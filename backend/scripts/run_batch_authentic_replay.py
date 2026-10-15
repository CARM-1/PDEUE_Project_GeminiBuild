#!/usr/bin/env python3
"""Replay captured Polymarket files with explicit auto-scenario assumptions."""
import argparse
from collections import defaultdict
import json
import hashlib
from pathlib import Path
import sys

# Support direct script execution from any working directory.
BACKEND = Path(__file__).resolve().parents[1]
REPOSITORY = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.domain.walk_forward_replay_harness import WalkForwardReplayHarness
from app.adapters.authentic_polymarket_tape_loader import parse_authentic_polymarket_tape

DEFAULT_TAPE_DIR = REPOSITORY / 'data/venues/polymarket'
DEFAULT_REPORT = BACKEND / 'reports/authentic_batch_replay_scorecard.json'
DEFAULT_MARKDOWN = REPOSITORY / 'reports/LATEST_REPLAY_SCORECARD.md'


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
    seen_trade_ids = set()
    for path in sorted(Path(tape_dir).glob('raw_trades_*.json')):
        try:
            scorecard = WalkForwardReplayHarness().run_authentic(path, auto_scenario=True)
            split = scorecard['waterfall']
            if sum(split.values()) != scorecard['net_pnl_cents']:
                raise ValueError('ADR-008 exact-cent conservation failed')
            scorecard['exact_cent_conservation'] = True
            scorecard['tape_path'] = _display_path(path)
            digest = scorecard['fixture_sha256']
            tape_bytes = path.read_bytes()
            if hashlib.sha256(tape_bytes).hexdigest() != digest:
                raise ValueError('capture changed during batch evaluation')
            ids = {trade.trade_id for trade in parse_authentic_polymarket_tape(tape_bytes)}
            if digest not in unique_results and ids & seen_trade_ids:
                raise ValueError('overlapping trade IDs across different captures')
            seen_trade_ids.update(ids)
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
        'total_initialization_trades': sum(result['initialization_trade_print_count'] for result in evaluated),
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
    unique = list(unique_results.values())
    unique_waterfall = {name: sum(result['waterfall'][name] for result in unique)
                        for name in waterfall}
    unique_summary = {
        'total_unique_trades': len(seen_trade_ids),
        'replayed_trade_count': sum(result['trade_print_count'] for result in unique),
        'initialization_trade_count': sum(result['initialization_trade_print_count'] for result in unique),
        'maker_fill_count': sum(len(result['fills']) for result in unique),
        'volume_deployed': sum(result['filled_quantity'] for result in unique),
        'deployed_cents': sum(result['deployed_cents'] for result in unique),
        'payout_cents': sum(result['payout_cents'] for result in unique),
        'fee_cents': sum(result['fee_cents'] for result in unique),
        'net_pnl_cents': sum(result['net_pnl_cents'] for result in unique),
        'waterfall': unique_waterfall,
    }
    unique_summary['exact_cent_conservation'] = bool(unique) and (
        sum(unique_waterfall.values()) == unique_summary['net_pnl_cents'])
    return {
        'schema_version': 2,
        'status': 'COMPLETED' if qualified else 'INCOMPLETE',
        'replay_mode': 'AUTO_SCENARIO_SIMULATION',
        'pnl_basis': 'SIMULATED_SETTLEMENT',
        'assumptions': {
            'pricing': 'Initial token print seeds a clipped 1..97-cent bid; ask is bid+2, '
                       'resting maker limit is bid+1, with five assumed lots ahead.',
            'model': 'Assumed spot=102000, strike=100000, volatility=0.60, rate=0.',
            'settlement': 'Assumed winning payout; not an official venue resolution.',
            'selection': 'Primary contract by normalized trade count; ID breaks ties.',
            'time_bounds': 'First token timestamp seeds the book. Decision is 1ns later; '
                           'all prints at that first timestamp are excluded from execution. '
                           'Expiry is 300s after the last selected token print.',
            'lookahead': 'Selection and expiry use full-capture metadata. Quotes use only '
                         'the initial print; spread, depth, model, and settlement remain assumptions.',
            'execution': 'Strategy D SELL flow at or below our limit consumes queue before '
                         'filling at the resting bid. BUY flow never fills a maker bid.',
            'aggregation': 'File totals include duplicate captures. Waterfall sums per-tape '
                           'allocations; it does not re-round aggregate PnL.',
        },
        'expected_tape_count': expected_tapes, 'expected_trade_count': expected_trades,
        'expected_counts_met': expected_counts_met, 'summary': summary,
        'unique_summary': unique_summary,
        'data_qualification': {
            'fresh_harvest_verified': False,
            'nonoverlapping_captures': bool(unique) and not summary['duplicate_tape_count'] and not summary['rejected_tapes'],
            'official_settlement_verified': False,
            'scope': 'Offline replay of existing captures; neither a new harvest nor venue profit certification.',
        },
        'duplicate_capture_groups': [
            {'fixture_sha256': digest, 'tape_paths': paths}
            for digest, paths in sorted(capture_groups.items()) if len(paths) > 1
        ],
        'results': results,
    }


def print_scorecard(report: dict) -> None:
    s = report['summary']
    u = report['unique_summary']
    split = u['waterfall']
    rows = [
        ('Status', report['status']),
        ('Tapes evaluated / expected', f"{s['total_tapes_evaluated']} / {report['expected_tape_count']}"),
        ('Trades parsed / expected', f"{s['total_trades_parsed']:,} / {report['expected_trade_count']:,}"),
        ('Replayed / seed / excluded trades', f"{s['total_trades_replayed']:,} / {s['total_initialization_trades']:,} / {s['total_trades_excluded']:,}"),
        ('Admitted / abstained / rejected', f"{s['admitted_executions']} / {s['abstained_executions']} / {s['rejected_tapes']}"),
        ('Unique / duplicate captures', f"{s['unique_tape_count']} / {s['duplicate_tape_count']}"),
        ('Total unique trades', u['total_unique_trades']),
        ('Unique fill events / deployed volume', f"{u['maker_fill_count']} / {u['volume_deployed']} lots"),
        ('Unique deployed capital (cents)', u['deployed_cents']),
        ('Unique net PnL (simulated cents)', u['net_pnl_cents']),
        ('SCMA 87% (cents)', split['scma_cents']),
        ('FAEP 3% (cents)', split['faep_cents']),
        ('CFCP 10% + residual (cents)', split['cfcp_cents']),
        ('ADR-008 exact-cent conservation', 'PASS' if s['exact_cent_conservation'] else 'FAIL'),
    ]
    print('=' * 76)
    print(' AUTHENTIC TAPE BATCH REPLAY - AUTO-SCENARIO SIMULATION')
    print(' Financial headline totals count each capture once; settlement is assumed.')
    print('-' * 76)
    for label, value in rows:
        print(f' {label:<39} {value}')
    print('=' * 76)


def render_markdown(report: dict) -> str:
    s, u = report['summary'], report['unique_summary']
    split = u['waterfall']
    return f"""# PDEUE WP-8P Maker Fill Calibration Scorecard

Source: `backend/reports/authentic_batch_replay_scorecard.json`.
Mode: captured trades with **simulated Strategy D maker execution and assumed settlement**.
The spread, five-lot queue, fair-value inputs, and winning payout are assumptions;
these are not observed Level 2 books or official realized venue profits.

| Metric | Unique-capture result |
| --- | ---: |
| Total unique trades | {u['total_unique_trades']} |
| Post-decision token prints replayed | {u['replayed_trade_count']} |
| Initialization prints excluded | {u['initialization_trade_count']} |
| Maker fill events | {u['maker_fill_count']} |
| Filled volume (lots) | {u['volume_deployed']} |
| Deployed capital (cents) | {u['deployed_cents']} |
| Settlement payout (simulated cents) | {u['payout_cents']} |
| Fees (cents) | {u['fee_cents']} |
| Net realized PnL (simulated cents) | {u['net_pnl_cents']} |

| ADR-008 allocation | Rule | Integer cents |
| --- | --- | ---: |
| SCMA | 87% floor on gains; all losses | {split['scma_cents']} |
| FAEP | 3% floor on gains | {split['faep_cents']} |
| CFCP | 10% plus residual on gains | {split['cfcp_cents']} |
| Total | Equals net PnL exactly | {sum(split.values())} |

Unique-capture cent conservation: **{'PASS' if u['exact_cent_conservation'] else 'FAIL'}**.

The batch evaluated {s['total_tapes_evaluated']} files and parsed {s['total_trades_parsed']}
records: {s['unique_tape_count']} unique captures and {s['duplicate_tape_count']} duplicate copies.
File-level admissions/abstentions/rejections: {s['admitted_executions']}/{s['abstained_executions']}/{s['rejected_tapes']}.
Financial headline metrics count each capture once. Repeated-file totals remain
in the JSON for comparison and must not be treated as independent executions.

The initial token print seeds the assumed best bid; ask is bid+2 cents and the
resting inside bid is bid+1. Five lots ahead must clear before fills. Decisions
follow the initial timestamp, and every print at that timestamp is excluded.
Only subsequent SELL prints at or below the limit consume queue; fills are priced
at the resting limit. Other outcome tokens and BUY prints cannot fill that bid.

The corrected harvester uses market-filtered offset pagination, exact condition
and YES-token verification, and cross-market hash uniqueness before writing files.
Fresh harvesting has not been verified for this offline report. Existing duplicate
captures remain preserved; their filename markets do not establish their contents'
settled-market provenance. Official settlement is not available for this simulation.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tape-dir', type=Path, default=DEFAULT_TAPE_DIR)
    parser.add_argument('--output', type=Path, default=DEFAULT_REPORT)
    parser.add_argument('--markdown-output', type=Path,
                        help='Markdown scorecard; defaults to reports/LATEST_REPLAY_SCORECARD.md for the default JSON output')
    parser.add_argument('--expected-tapes', type=int, default=30)
    parser.add_argument('--expected-trades', type=int, default=3000)
    args = parser.parse_args()
    if args.expected_tapes <= 0 or args.expected_trades <= 0:
        parser.error('expected counts must be positive')
    report = run_batch(args.tape_dir, expected_tapes=args.expected_tapes, expected_trades=args.expected_trades)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    markdown_output = args.markdown_output
    if markdown_output is None and args.output.resolve() == DEFAULT_REPORT.resolve():
        markdown_output = DEFAULT_MARKDOWN
    if markdown_output:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(render_markdown(report), encoding='utf-8')
    print_scorecard(report)
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
