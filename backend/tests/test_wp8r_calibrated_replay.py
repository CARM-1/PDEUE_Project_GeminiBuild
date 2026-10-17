from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.adapters.authentic_tape_router import parse_venue_tape
from app.adapters.authentic_polymarket_tape_loader import MarketTradePrint
from app.adapters.authentic_weather_tape_loader import WeatherReplayScenario
from app.domain.authentic_replay_calibration import HORIZON_NS, initial_scenario, run_calibrated
from scripts.run_batch_authentic_replay import run_batch

ROOT = Path(__file__).resolve().parents[2]
BASE = 1735689600000000000


def print_(tid, cid='A', ts=BASE, price=45, volume=1, asset=None):
    return MarketTradePrint(tid, cid, price, volume, ts, 'SELL', 'Test vector', asset)


def test_future_contract_counts_prices_and_end_time_cannot_change_calibration():
    seed = [print_('first'), print_('other', 'Z')]
    scenario, queue, asset = initial_scenario(seed + [print_('future', 'Z', BASE + 1_000_000_000)])
    future = [print_(str(i), 'Z', BASE + (i + 1) * HORIZON_NS, 99, 999999) for i in range(20)]
    assert initial_scenario(seed + future) == (scenario, queue, asset)
    assert scenario.contract_id == 'A'
    assert scenario.expiry_ns == BASE + HORIZON_NS
    assert scenario.observed_at_ns == BASE
    assert scenario.decision_at_ns == BASE + 1


def test_initial_book_uses_conservative_depth_and_inside_price():
    book = dict(contract_id='A', timestamp_ns=BASE, bids=[[40, 11], [39, 20]], asks=[[44, 10]])
    s, queue, _ = initial_scenario([print_('seed')], book)
    assert (s.best_bid_cents, s.best_ask_cents, queue) == (40, 44, 11)
    assert s.best_bid_cents + 1 < s.best_ask_cents


@pytest.mark.parametrize('change', [
    {'timestamp_ns': BASE + 1}, {'contract_id': 'OTHER'}, {'bids': [[45, True]]},
    {'bids': [[45, 1.5]]}, {'asks': [[44, 1]]}, {'bids': [[45, 1], [45, 2]]},
    {'bids': []}, {'asks': None},
])
def test_invalid_initial_books_fail_closed(tmp_path, change):
    path = tmp_path / 'raw_trades.json'
    payload = json.loads((ROOT / 'data/venues/kalshi/raw_trades_macro.json').read_text())
    payload['initial_book']['contract_id'] = 'A'
    for row in payload['trades']:
        row['ticker'] = 'A'
    payload['initial_book'].update(change)
    path.write_text(json.dumps(payload))
    report = run_batch(venue_dirs={'kalshi': tmp_path})
    assert report['status'] == 'INCOMPLETE'
    assert report['summary']['rejected_tapes'] == 1
    result = report['results'][0]
    assert result['status'] == result['reason'] == 'ABSTAINED'
    assert result['fills'] == []
    assert result['deployed_cents'] == result['net_pnl_cents'] == 0


def test_weather_execution_uses_only_separate_trade_flow_and_enforces_expiry(tmp_path):
    source = ROOT / 'data/venues/weather/raw_observations_kjfk.json'
    result = run_calibrated(source, 'weather')
    assert result['filled_quantity'] == 10
    assert result['initial_q_ahead'] == 7
    assert result['initialization_trade_print_count'] == 2
    assert result['outside_horizon_trade_print_count'] == 1
    assert [fill['quantity'] for fill in result['fills']] == [4, 6]
    assert all(fill['price_cents'] == 46 for fill in result['fills'])
    assert result['weather_evaluation']['post_expiry_excluded_count'] == 2
    payload = json.loads(source.read_text())
    for feature in payload['features'][1:]:
        feature['properties']['temperature']['value'] = 100
    changed = tmp_path / 'weather.json'
    changed.write_text(json.dumps(payload))
    rerun = run_calibrated(changed, 'weather')
    for key in ('scenario', 'fills', 'deployed_cents', 'net_pnl_cents'):
        assert result[key] == rerun[key]


def test_observation_only_weather_calibrates_bounds_but_never_executes():
    result = run_calibrated(ROOT / 'data/venues/weather/raw_observations_kord.json', 'weather')
    assert result['abstention_detail'] == 'NO_EXECUTION_TAPE'
    assert result['parsed_observation_count'] == 5
    assert result['fills'] == []
    assert result['deployed_cents'] == result['net_pnl_cents'] == 0


@pytest.mark.parametrize('bad', ['corrupt', 'unknown_contract', 'duplicate'])
def test_bad_embedded_execution_tape_rejects_entire_weather_feed(tmp_path, bad):
    payload = json.loads((ROOT / 'data/venues/weather/raw_observations_kjfk.json').read_text())
    rows = payload['execution_tape']['trades']
    if bad == 'corrupt':
        rows[-1]['count'] = 'NaN'
    elif bad == 'unknown_contract':
        rows[-1]['ticker'] = 'UNKNOWN'
    else:
        rows.append(rows[0])
    (tmp_path / 'weather.json').write_text(json.dumps(payload))
    report = run_batch(venue_dirs={'weather': tmp_path})
    assert report['status'] == 'INCOMPLETE'
    assert report['results'][0]['reason'] == 'ABSTAINED'
    assert report['unique_summary']['maker_fill_count'] == 0


def test_all_venues_support_strategy_d_and_one_conserved_waterfall(tmp_path):
    poly = tmp_path / 'poly'
    poly.mkdir()
    (poly / 'raw_trades_test.json').write_text(json.dumps([
        dict(transactionHash=tid, conditionId='P', asset='YES', title='Synthetic vector',
             price=.45, size=size, timestamp=1735689600 + seconds, side=side)
        for tid, size, seconds, side in [('seed', 999, 0, 'SELL'), ('buy', 999, 1, 'BUY'),
                                         ('queue', 3, 2, 'SELL'), ('fill', 12, 3, 'SELL')]
    ]))
    report = run_batch(venue_dirs={'polymarket': poly, 'kalshi': ROOT / 'data/venues/kalshi',
                                  'weather': ROOT / 'data/venues/weather'})
    assert report['status'] == 'COMPLETED'
    assert all(entry['maker_fill_count'] > 0 for entry in report['by_venue'].values())
    assert report['unique_summary']['maker_fill_count'] == 7
    assert report['unique_summary']['net_pnl_cents'] == 2310
    assert sum(report['unique_summary']['waterfall'].values()) == 2310
    assert sum(entry['net_pnl_cents'] for entry in report['by_venue'].values()) == 2310


def test_external_scenario_overrides_calibration_even_when_enabled(tmp_path):
    payload = (ROOT / 'data/venues/kalshi/raw_trades_macro.json').read_bytes()
    path = tmp_path / 'trades.json'
    path.write_bytes(payload)
    prints = parse_venue_tape(payload, 'kalshi')
    s, _, _ = initial_scenario(prints)
    s = replace(s, observed_at_ns=BASE - 2, decision_at_ns=BASE - 1,
                expiry_ns=BASE + 2 * HORIZON_NS, settlement_payout_cents=0)
    config = {'kalshi': {path.name: {'scenario': asdict(s), 'queue_ahead': 5}}}
    report = run_batch(venue_dirs={'kalshi': tmp_path}, scenario_manifest=config)
    result = report['results'][0]
    assert result['independent_scenario_supplied'] is True
    assert result['payout_cents'] == 0
    assert result['net_pnl_cents'] < 0
    assert 'scenario_source' not in result
    assert report['replay_mode'] == 'INDEPENDENT_SCENARIO_REPLAY'


def test_weather_accepts_independent_execution_and_settlement_inputs(tmp_path):
    payload = json.loads((ROOT / 'data/venues/weather/raw_observations_kjfk.json').read_text())
    payload['execution_tape']['trades'] = payload['execution_tape']['trades'][:-1]
    path = tmp_path / 'weather.json'
    path.write_text(json.dumps(payload))
    s, _, _ = initial_scenario(list(parse_venue_tape(path.read_bytes(), 'weather').execution_prints))
    execution = replace(s, observed_at_ns=BASE - 2, decision_at_ns=BASE - 1, settlement_payout_cents=0)
    bounds = WeatherReplayScenario(s.contract_id, 'KJFK', BASE - 2, BASE - 1, s.expiry_ns)
    config = {'weather': {path.name: {'scenario': asdict(bounds), 'execution_scenario': asdict(execution),
                                     'queue_ahead': 5}}}
    report = run_batch(venue_dirs={'weather': tmp_path}, scenario_manifest=config)
    assert report['status'] == 'COMPLETED'
    assert report['by_venue']['weather']['maker_fill_count'] > 0
    assert report['by_venue']['weather']['net_pnl_cents'] == -460
    config['weather'][path.name]['execution_scenario']['expiry_ns'] += 1
    rejected = run_batch(venue_dirs={'weather': tmp_path}, scenario_manifest=config)
    assert rejected['status'] == 'INCOMPLETE'
    assert rejected['results'][0]['reason'] == 'ABSTAINED'


def test_calibrate_cli_flag_and_opt_out(tmp_path):
    command = [sys.executable, str(ROOT / 'backend/scripts/run_batch_authentic_replay.py'),
               '--venues-root', str(ROOT / 'data/venues'), '--output', str(tmp_path / 'report.json')]
    for flag in ('--calibrate', '--no-calibrate'):
        subprocess.run(command + [flag], capture_output=True, check=True, timeout=10)
        report = json.loads((tmp_path / 'report.json').read_text())
        assert bool(report['unique_summary']['maker_fill_count']) == (flag == '--calibrate')
