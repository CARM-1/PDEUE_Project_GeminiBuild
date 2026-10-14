#!/usr/bin/env python3
"""Replay captured Polymarket files with explicit auto-scenario assumptions."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

# Support direct script execution from any working directory.
BACKEND = Path(__file__).resolve().parents[1]
REPOSITORY = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.domain.walk_forward_replay_harness import WalkForwardReplayHarness

DEFAULT_TAPE_DIR = REPOSITORY / 'data/venues/polymarket'
DEFAULT_REPORT = BACKEND / 'reports/authentic_batch_replay_scorecard.json'


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPOSITORY))
    except ValueError:
        return str(path.resolve())


def run_batch(tape_dir: Path = DEFAULT_TAPE_DIR, *, expected_tapes: int = 30,
              expected_trades: int = 3000) -> dict:
    """Evaluate every matching file; record rejections without admitting bad data.

    File totals intentionally include repeated captures. Unique capture totals
    are reported separately using the full-file digest, not the filename.
    """
    results = []
    capture_groups = defaultdict(list)
    unique_results = {}
    for path in sorted(Path(tape_dir).glob('raw_trades_*.json')):
        try:
            scorecard = WalkForwardReplayHarness().run_authentic(path, auto_scenario=True)
            split = scorecard['waterfall']
            if sum(split.values()) != scorecard['net_pnl_cents']:
                raise ValueError('ADR-008 exact-cent conservation failed')
            scorecard['exact_cent_conservation'] = True
            scorecard['tape_path'] = _display_path(path)
            digest = scorecard['fixture_sha256']
            capture_groups[digest].append(scorecard['tape_path'])
            unique_results.setdefault(digest, scorecard)
            results.append(scorecard)
        except (OSError, ValueError) as exc:
            results.append({
                'tape_path': _display_path(path), 'status': 'REJECTED',
                'reason': 'INVALID_TAPE', 'error': str(exc),
            })
    evaluated = [result for result in results if result['status'] != 'REJECTED']
    waterfall = {name: sum(result['waterfall'][name] for result in evaluated)
                 for name in ('scma_cents', 'faep_cents', 'cfcp_cents')}
    pnl = sum(result['net_pnl_cents'] for result in evaluated)
    conservation = bool(evaluated) and sum(waterfall.values()) == pnl and all(
        result['exact_cent_conservation'] for result in evaluated)
    summary = {
        'total_tapes_evaluated': len(results),
        'successful_tapes': len(evaluated), 'rejected_tapes': len(results) - len(evaluated),
        'total_raw_trade_records': sum(result['raw_trade_record_count'] for result in evaluated),
        'total_trades_parsed': sum(result['parsed_trade_print_count'] for result in evaluated),
        'total_trades_replayed': sum(result['trade_print_count'] for result in evaluated),
        'total_trades_excluded': sum(result['excluded_trade_print_count'] for result in evaluated),
        'admitted_executions': sum(result['reason'] == 'ADMITTED' for result in evaluated),
        'abstained_executions': sum(result['reason'] == 'ABSTAINED' for result in evaluated),
        'cumulative_fill_count': sum(len(result['fills']) for result in evaluated),
        'volume_deployed': sum(result['filled_quantity'] for result in evaluated),
        'deployed_cents': sum(result['deployed_cents'] for result in evaluated),
        'fee_cents': sum(result['fee_cents'] for result in evaluated),
        'payout_cents': sum(result['payout_cents'] for result in evaluated),
        'realized_net_pnl_cents': pnl, 'waterfall': waterfall,
        'exact_cent_conservation': conservation,
        'unique_tape_count': len(unique_results),
        'duplicate_tape_count': len(evaluated) - len(unique_results),
        'unique_capture_trade_print_count': sum(result['parsed_trade_print_count']
                                                for result in unique_results.values()),
        'unique_capture_replayed_trade_count': sum(result['trade_print_count']
                                                   for result in unique_results.values()),
        'unique_capture_net_pnl_cents': sum(result['net_pnl_cents']
                                           for result in unique_results.values()),
    }
    expected_counts_met = (len(results) == expected_tapes and
                           summary['total_trades_parsed'] == expected_trades)
    qualified = bool(evaluated) and not summary['rejected_tapes'] and expected_counts_met and conservation
    return {
        'schema_version': 1,
        'status': 'COMPLETED' if qualified else 'INCOMPLETE',
        'replay_mode': 'AUTO_SCENARIO_SIMULATION',
        'pnl_basis': 'SIMULATED_SETTLEMENT',
        'assumptions': {
            'pricing': 'Fixed 1-cent bid / 99-cent ask; no book inferred from prints.',
            'model': 'Assumed spot=strike=100000, volatility=0.60, rate=0.',
            'settlement': 'Assumed winning payout; not an official venue resolution.',
            'selection': 'Primary contract by normalized trade count; ID breaks ties.',
            'time_bounds': 'Observation/decision precede first selected print by 2s/1s; '
                           'expiry is 300s after the last selected print.',
            'lookahead': 'Selection and expiry use full-capture metadata. Quotes do not '
                         'use future trade prices. This is not a certified pre-trade strategy.',
            'aggregation': 'File totals include duplicate captures. Waterfall sums per-tape '
                           'allocations; it does not re-round aggregate PnL.',
        },
        'expected_tape_count': expected_tapes, 'expected_trade_count': expected_trades,
        'expected_counts_met': expected_counts_met, 'summary': summary,
        'duplicate_capture_groups': [
            {'fixture_sha256': digest, 'tape_paths': paths}
            for digest, paths in sorted(capture_groups.items()) if len(paths) > 1
        ],
        'results': results,
    }


def print_scorecard(report: dict) -> None:
    s = report['summary']
    split = s['waterfall']
    rows = [
        ('Status', report['status']),
        ('Tapes evaluated / expected', f"{s['total_tapes_evaluated']} / {report['expected_tape_count']}"),
        ('Trades parsed / expected', f"{s['total_trades_parsed']:,} / {report['expected_trade_count']:,}"),
        ('Selected / excluded trades', f"{s['total_trades_replayed']:,} / {s['total_trades_excluded']:,}"),
        ('Admitted / abstained / rejected', f"{s['admitted_executions']} / {s['abstained_executions']} / {s['rejected_tapes']}"),
        ('Unique / duplicate captures', f"{s['unique_tape_count']} / {s['duplicate_tape_count']}"),
        ('Unique capture trades', s['unique_capture_trade_print_count']),
        ('Fill events / deployed volume', f"{s['cumulative_fill_count']} / {s['volume_deployed']} lots"),
        ('Deployed capital (cents)', s['deployed_cents']),
        ('Realized net PnL (simulated cents)', s['realized_net_pnl_cents']),
        ('SCMA 87% (cents)', split['scma_cents']),
        ('FAEP 3% (cents)', split['faep_cents']),
        ('CFCP 10% + residual (cents)', split['cfcp_cents']),
        ('ADR-008 exact-cent conservation', 'PASS' if s['exact_cent_conservation'] else 'FAIL'),
    ]
    print('=' * 76)
    print(' AUTHENTIC TAPE BATCH REPLAY - AUTO-SCENARIO SIMULATION')
    print(' File totals include repeated captures; settlement is assumed.')
    print('-' * 76)
    for label, value in rows:
        print(f' {label:<39} {value}')
    print('=' * 76)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tape-dir', type=Path, default=DEFAULT_TAPE_DIR)
    parser.add_argument('--output', type=Path, default=DEFAULT_REPORT)
    parser.add_argument('--expected-tapes', type=int, default=30)
    parser.add_argument('--expected-trades', type=int, default=3000)
    args = parser.parse_args()
    if args.expected_tapes <= 0 or args.expected_trades <= 0:
        parser.error('expected counts must be positive')
    report = run_batch(args.tape_dir, expected_tapes=args.expected_tapes, expected_trades=args.expected_trades)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print_scorecard(report)
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
