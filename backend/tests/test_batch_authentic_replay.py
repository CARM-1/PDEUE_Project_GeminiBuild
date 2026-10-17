import json
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys

from scripts.run_batch_authentic_replay import run_batch
from app.domain.walk_forward_replay_harness import IndependentReplayScenario
from app.adapters.authentic_weather_tape_loader import WeatherReplayScenario


def make_capture(tmp_path, name='raw_trades_a.json'):
    path = tmp_path / name
    path.write_text(json.dumps([
        dict(transactionHash='a', conditionId='PRIMARY', price=.02, size=10,
             timestamp=1735689600, side='SELL', title='Synthetic qualification vector'),
        dict(transactionHash='b', conditionId='PRIMARY', price=.02, size=3,
             timestamp=1735689601, side='SELL', title='Synthetic qualification vector'),
        dict(transactionHash='d', conditionId='PRIMARY', price=.02, size=12,
             timestamp=1735689602, side='SELL', title='Synthetic qualification vector'),
        dict(transactionHash='c', conditionId='SECONDARY', price=.02, size=999,
             timestamp=1735689601, side='SELL', title='Synthetic qualification vector'),
    ]))
    return path


def test_batch_preserves_file_totals_and_discloses_duplicate_captures(tmp_path):
    first = make_capture(tmp_path)
    second = tmp_path / 'raw_trades_b.json'
    second.write_bytes(first.read_bytes())
    report = run_batch(tmp_path, expected_tapes=2, expected_trades=8)
    summary = report['summary']
    assert report['status'] == 'COMPLETED'
    assert report['pnl_basis'] == 'SIMULATED_SETTLEMENT'
    assert summary['total_tapes_evaluated'] == summary['admitted_executions'] == 2
    assert summary['abstained_executions'] == summary['rejected_tapes'] == 0
    assert summary['total_trades_parsed'] == summary['total_raw_trade_records'] == 8
    assert summary['total_trades_replayed'] == 4
    assert summary['total_trades_excluded'] == 2
    assert summary['unique_tape_count'] == summary['duplicate_tape_count'] == 1
    assert summary['unique_capture_trade_print_count'] == 4
    assert summary['unique_capture_replayed_trade_count'] == 2
    assert summary['volume_deployed'] == 20
    assert summary['cumulative_fill_count'] == 2
    assert summary['deployed_cents'] == 60
    assert summary['realized_net_pnl_cents'] == 1940
    assert summary['waterfall'] == {'scma_cents': 1686, 'faep_cents': 58, 'cfcp_cents': 196}
    assert summary['unique_capture_net_pnl_cents'] == 970
    assert report['unique_summary']['total_unique_trades'] == 4
    assert report['unique_summary']['maker_fill_count'] == 1
    assert report['unique_summary']['net_pnl_cents'] == 970
    assert sum(summary['waterfall'].values()) == summary['realized_net_pnl_cents']
    assert summary['exact_cent_conservation'] is True
    assert len(report['duplicate_capture_groups']) == 1
    assert len(report['duplicate_capture_groups'][0]['tape_paths']) == 2
    assert report == run_batch(tmp_path, expected_tapes=2, expected_trades=8)


def test_batch_rejects_corruption_and_reports_actual_counts(tmp_path):
    make_capture(tmp_path)
    (tmp_path / 'raw_trades_bad.json').write_text('[{"invalid":"row"}]')
    report = run_batch(tmp_path, expected_tapes=2, expected_trades=8)
    assert report['status'] == 'INCOMPLETE'
    assert report['expected_counts_met'] is False
    summary = report['summary']
    assert summary['rejected_tapes'] == 1
    assert summary['total_tapes_evaluated'] == 2
    assert summary['total_trades_parsed'] == 4
    assert summary['realized_net_pnl_cents'] == 970
    rejected = report['results'][1]
    assert rejected['status'] == rejected['reason'] == 'ABSTAINED'
    assert rejected['abstention_detail'] == 'INVALID_TAPE'
    assert rejected['validation_status'] == 'REJECTED'
    assert rejected['fills'] == []
    assert 'error' in rejected


def test_batch_cli_runs_from_other_directory_and_exits_nonzero_for_missing_data(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    tapes = tmp_path / 'tapes'
    tapes.mkdir()
    make_capture(tapes)
    output = tmp_path / 'report.json'
    command = [sys.executable, str(backend / 'scripts/run_batch_authentic_replay.py'),
               f'--tape-dir={tapes}', f'--output={output}', '--expected-tapes=1', '--expected-trades=4']
    completed = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0
    assert json.loads(output.read_text())['status'] == 'COMPLETED'
    assert '1 / 1' in completed.stdout
    assert 'ADR-008 exact-cent conservation' in completed.stdout
    tapes.joinpath('raw_trades_a.json').unlink()
    missing = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert missing.returncode == 1
    report = json.loads(output.read_text())
    assert report['status'] == 'INCOMPLETE'
    assert report['summary']['total_tapes_evaluated'] == 0


def test_different_capture_digests_cannot_double_count_shared_trade_ids(tmp_path):
    first = make_capture(tmp_path)
    rows = json.loads(first.read_text())
    rows.append(dict(transactionHash='extra', conditionId='PRIMARY', price=.02, size=1,
                     timestamp=1735689603, side='SELL', title='Synthetic qualification vector'))
    (tmp_path / 'raw_trades_b.json').write_text(json.dumps(rows))
    report = run_batch(tmp_path, expected_tapes=2, expected_trades=9)
    assert report['status'] == 'INCOMPLETE'
    assert report['summary']['rejected_tapes'] == 1
    assert report['unique_summary']['total_unique_trades'] == 4
    assert 'overlapping' in report['results'][1]['error']


def multicategory_captures(tmp_path):
    directories = {venue: tmp_path / venue for venue in ('polymarket', 'kalshi', 'weather')}
    for directory in directories.values():
        directory.mkdir()
    poly_path = make_capture(directories['polymarket'])
    kalshi_path = directories['kalshi'] / 'raw_trades_kalshi.json'
    kalshi_path.write_text(json.dumps({'trades': [
        dict(trade_id='a', ticker='KX-TEST-YES', yes_price=46, count=3, ts=1735689600, taker_side='no'),
        dict(trade_id='b', ticker='KX-TEST-YES', yes_price=46, count=999, ts=1735689601, taker_side='yes'),
        dict(trade_id='c', ticker='KX-TEST-YES', yes_price=45, count=12, ts=1735689602, taker_side='no'),
    ]}))
    weather_path = directories['weather'] / 'raw_observations_jfk.json'
    weather_path.write_text(json.dumps({
        'observations': [dict(observation_id='a', station_id='KJFK', timestamp=1735689600, temperature_f=70),
                         dict(observation_id='b', station_id='KJFK', timestamp=1735689601, temperature_f=71)],
        'strike_ladder': [dict(contract_id='JFK-70-72', station_id='KJFK', expiry=1735689900, lower_f=70, upper_f=72)],
    }))
    base = 1735689600 * 1_000_000_000
    poly = IndependentReplayScenario('PRIMARY', base - 2_000_000_000, base - 1_000_000_000,
                                    base + 300_000_000_000, .7, 100, 1, 4, {1: 5})
    kalshi = IndependentReplayScenario('KX-TEST-YES', base - 2_000_000_000, base - 1_000_000_000,
                                      base + 300_000_000_000, .7, 100)
    weather = WeatherReplayScenario('JFK-70-72', 'KJFK', base - 2_000_000_000,
                                    base - 1_000_000_000, base + 300_000_000_000)
    manifest = {
        'polymarket': {poly_path.name: {'scenario': asdict(poly), 'queue_ahead': 5}},
        'kalshi': {kalshi_path.name: {'scenario': asdict(kalshi), 'queue_ahead': 5}},
        'weather': {weather_path.name: asdict(weather)},
    }
    return directories, manifest


def test_multicategory_independent_scenarios_reconcile_one_cross_venue_waterfall(tmp_path):
    directories, manifest = multicategory_captures(tmp_path)
    report = run_batch(venue_dirs=directories, scenario_manifest=manifest)
    assert report['status'] == 'COMPLETED'
    assert report['replay_mode'] == 'INDEPENDENT_SCENARIO_REPLAY'
    assert report['missing_venues'] == []
    assert report['data_qualification']['venue_coverage_complete'] is True
    assert report['summary']['total_markets_evaluated'] == 4
    assert report['summary']['total_trades_parsed'] == 7
    assert report['summary']['total_observations_parsed'] == 2
    assert report['summary']['total_observations_evaluated'] == 2
    assert report['summary']['total_prints_parsed'] == 9
    assert report['unique_summary']['total_unique_trades'] == 7
    assert report['unique_summary']['total_unique_observations'] == 2
    # Repeated ID strings across venues refer to independent records.
    assert report['summary']['rejected_tapes'] == 0
    assert report['by_venue']['kalshi']['net_pnl_cents'] == 540
    assert report['by_venue']['weather']['maker_fill_count'] == 0
    assert report['by_venue']['polymarket']['net_pnl_cents'] == 980
    assert report['unique_summary']['net_pnl_cents'] == 1520
    assert report['unique_summary']['waterfall'] == {'scma_cents': 1321, 'faep_cents': 45, 'cfcp_cents': 154}
    assert sum(report['unique_summary']['waterfall'].values()) == report['unique_summary']['net_pnl_cents']


def test_multicategory_batch_opt_out_abstains_without_external_scenarios(tmp_path):
    directories, _ = multicategory_captures(tmp_path)
    report = run_batch(venue_dirs=directories, auto_scenario=False)
    assert report['summary']['admitted_executions'] == 0
    assert report['summary']['abstained_executions'] == 3
    assert report['summary']['total_trades_replayed'] == 0
    assert report['unique_summary']['maker_fill_count'] == 0
    assert report['unique_summary']['deployed_cents'] == 0
    assert all(result['abstention_detail'] == 'MISSING_INDEPENDENT_REPLAY_SCENARIO' for result in report['results'])


def test_multicategory_cli_discovers_all_venues_and_regenerates_both_reports(tmp_path):
    _, manifest = multicategory_captures(tmp_path)
    config = tmp_path / 'scenario_manifest.json'
    config.write_text(json.dumps(manifest))
    output, markdown = tmp_path / 'scorecard.json', tmp_path / 'scorecard.md'
    backend = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(backend / 'scripts/run_batch_authentic_replay.py'),
               f'--venues-root={tmp_path}', f'--scenario-manifest={config}',
               f'--output={output}', f'--markdown-output={markdown}']
    completed = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=True, timeout=10)
    report = json.loads(output.read_text())
    assert report['summary']['total_tapes_evaluated'] == 3
    assert report['by_venue']['kalshi']['admitted'] == 1
    assert '| weather | EVALUATED |' in markdown.read_text()
    assert 'NOAA temperatures' in markdown.read_text()
    assert 'kalshi' in completed.stdout
