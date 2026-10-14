import json
from pathlib import Path
import subprocess
import sys

from scripts.run_batch_authentic_replay import run_batch


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
    assert rejected['status'] == 'REJECTED'
    assert rejected['reason'] == 'INVALID_TAPE'
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
