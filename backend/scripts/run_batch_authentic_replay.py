#!/usr/bin/env python3
"""Replay captured trade tapes and evaluate NOAA observations across venues."""
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
from app.adapters.authentic_tape_router import parse_venue_tape, record_ids, contract_ids
from app.adapters.authentic_weather_tape_loader import WeatherTape
from run_walk_forward_replay import scenario_from_mapping

DEFAULT_TAPE_DIR = REPOSITORY / 'data/venues/polymarket'
DEFAULT_REPORT = BACKEND / 'reports/authentic_batch_replay_scorecard.json'
DEFAULT_MARKDOWN = REPOSITORY / 'reports/LATEST_REPLAY_SCORECARD.md'
DEFAULT_VENUES_ROOT = REPOSITORY / 'data/venues'


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPOSITORY))
    except ValueError:
        return str(path.resolve())


def discover_tapes(venue_dirs: dict) -> list[tuple[str, Path]]:
    discovered = set()
    for venue, directories in venue_dirs.items():
        if venue not in ('polymarket', 'kalshi', 'weather'):
            raise ValueError(f'unsupported replay venue: {venue}')
        for directory in directories if isinstance(directories, (list, tuple)) else [directories]:
            pattern = 'raw_trades_*.json' if venue == 'polymarket' else '*.json'
            for path in Path(directory).rglob(pattern):
                if path.is_file() and not any(word in path.name.lower() for word in ('manifest', 'scenario', 'ladder')):
                    discovered.add((venue, path.resolve()))
    return sorted(discovered)


def run_batch(tape_dir: Path = DEFAULT_TAPE_DIR, *, expected_tapes: int | None = None,
              expected_trades: int | None = None, venue_dirs: dict | None = None,
              scenario_manifest: dict | None = None, auto_scenario: bool | None = None) -> dict:
    """Evaluate every matching file; record rejections without admitting bad data.

    File totals intentionally include repeated captures. Unique capture totals
    are reported separately using the full-file digest, not the filename.
    """
    # Preserve the legacy single-directory calibration API; new multi-venue
    # callers and the CLI require explicit opt-in to Polymarket calibration.
    if auto_scenario is None:
        auto_scenario = venue_dirs is None
    venue_dirs = venue_dirs if venue_dirs is not None else {'polymarket': tape_dir}
    scenario_manifest = {} if scenario_manifest is None else scenario_manifest
    if not isinstance(scenario_manifest, dict) or any(venue not in venue_dirs for venue in scenario_manifest):
        raise ValueError('scenario manifest must map requested venues to per-file scenarios')
    results = []
    capture_groups = defaultdict(list)
    unique_results = {}
    seen_trade_ids = set()
    seen_record_ids, seen_observation_ids, seen_markets = set(), set(), set()
    tapes = discover_tapes(venue_dirs)
    for venue, path in tapes:
        try:
            configs = scenario_manifest.get(venue, {})
            if not isinstance(configs, dict):
                raise ValueError('per-venue scenario configuration must be an object')
            config = configs.get(_display_path(path), configs.get(path.name))
            scenario, queue_ahead, strategy_d = None, None, False
            if config is not None:
                if not isinstance(config, dict):
                    raise ValueError('per-file scenario must be an object')
                scenario = scenario_from_mapping(config.get('scenario', config), venue)
                queue_ahead = config.get('queue_ahead') if 'scenario' in config else None
                strategy_d = config.get('strategy_d', False) if 'scenario' in config else False
            scorecard = WalkForwardReplayHarness(scenario, queue_ahead=queue_ahead,
                                                 strategy_d=strategy_d).run_authentic(
                path, venue=venue, auto_scenario=auto_scenario)
            scorecard['independent_scenario_supplied'] = scenario is not None
            split = scorecard['waterfall']
            if sum(split.values()) != scorecard['net_pnl_cents']:
                raise ValueError('ADR-008 exact-cent conservation failed')
            scorecard['exact_cent_conservation'] = True
            scorecard['tape_path'] = _display_path(path)
            digest = scorecard['fixture_sha256']
            tape_bytes = path.read_bytes()
            if hashlib.sha256(tape_bytes).hexdigest() != digest:
                raise ValueError('capture changed during batch evaluation')
            parsed = parse_venue_tape(tape_bytes, venue)
            ids = {(venue, record_id) for record_id in record_ids(parsed)}
            capture_key = (venue, digest)
            if capture_key not in unique_results and ids & seen_record_ids:
                raise ValueError('overlapping trade IDs across different captures')
            seen_record_ids.update(ids)
            if isinstance(parsed, WeatherTape):
                seen_observation_ids.update(ids)
            else:
                seen_trade_ids.update(ids)
            seen_markets.update((venue, contract_id) for contract_id in contract_ids(parsed))
            capture_groups[capture_key].append(scorecard['tape_path'])
            unique_results.setdefault(capture_key, scorecard)
            results.append(scorecard)
        except (OSError, ValueError) as exc:
            results.append({
                'tape_path': _display_path(path), 'venue': venue, 'status': 'REJECTED',
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
        'total_markets_evaluated': len(seen_markets),
        'markets_with_independent_scenarios': len({(result['venue'], result['contract_id'])
            for result in evaluated if result['independent_scenario_supplied'] and result['contract_id'] is not None}),
        'total_observations_parsed': sum(result.get('parsed_observation_count', 0) for result in evaluated),
        'total_observations_evaluated': sum(
            result.get('weather_evaluation', {}).get('pre_decision_observation_count', 0)
            + result.get('weather_evaluation', {}).get('replay_observation_count', 0) for result in evaluated),
        'successful_tapes': len(evaluated), 'rejected_tapes': len(results) - len(evaluated),
        'total_raw_trade_records': sum(result['raw_trade_record_count'] for result in evaluated),
        'total_trades_parsed': sum(result['parsed_trade_print_count'] for result in evaluated),
        'total_trades_replayed': sum(result['replayed_trade_print_count'] for result in evaluated),
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
        'unique_capture_replayed_trade_count': sum(result['replayed_trade_print_count']
                                                   for result in unique_results.values()),
        'unique_capture_net_pnl_cents': sum(result['net_pnl_cents']
                                           for result in unique_results.values()),
    }
    summary['total_prints_parsed'] = summary['total_trades_parsed'] + summary['total_observations_parsed']
    summary['total_prints_filtered'] = summary['total_trades_excluded'] + sum(
        result.get('weather_evaluation', {}).get('post_expiry_excluded_count', 0)
        + result.get('weather_evaluation', {}).get('other_station_excluded_count', 0) for result in evaluated)
    expected_counts_met = ((expected_tapes is None or len(results) == expected_tapes) and
                           (expected_trades is None or summary['total_trades_parsed'] == expected_trades))
    qualified = bool(evaluated) and not summary['rejected_tapes'] and expected_counts_met and conservation
    unique = list(unique_results.values())
    unique_waterfall = {name: sum(result['waterfall'][name] for result in unique)
                        for name in waterfall}
    unique_summary = {
        'total_unique_trades': len(seen_trade_ids),
        'total_unique_observations': len(seen_observation_ids),
        'replayed_trade_count': sum(result['replayed_trade_print_count'] for result in unique),
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
    by_venue = {}
    for venue in venue_dirs:
        entries = [result for result in evaluated if result['venue'] == venue]
        financial = [result for result in unique if result['venue'] == venue]
        by_venue[venue] = {
            'tape_count': sum(result['venue'] == venue for result in results),
            'status': 'EVALUATED' if entries else 'NO_VALID_TAPES' if any(v == venue for v, _ in tapes) else 'NO_TAPES',
            'market_count': sum(v == venue for v, _ in seen_markets),
            'trade_print_count': sum(result['parsed_trade_print_count'] for result in entries),
            'observation_count': sum(result.get('parsed_observation_count', 0) for result in entries),
            'admitted': sum(result['reason'] == 'ADMITTED' for result in entries),
            'abstained': sum(result['reason'] == 'ABSTAINED' for result in entries),
            'maker_fill_count': sum(len(result['fills']) for result in financial),
            'deployed_cents': sum(result['deployed_cents'] for result in financial),
            'net_pnl_cents': sum(result['net_pnl_cents'] for result in financial),
            'waterfall': {name: sum(result['waterfall'][name] for result in financial) for name in waterfall},
        }
    return {
        'schema_version': 3,
        'status': 'COMPLETED' if qualified else 'INCOMPLETE',
        'replay_mode': 'AUTO_SCENARIO_SIMULATION' if auto_scenario else 'INDEPENDENT_SCENARIO_REPLAY',
        'pnl_basis': 'SIMULATED_SETTLEMENT' if auto_scenario else 'EXTERNAL_SCENARIO_SETTLEMENT_OR_ABSTENTION',
        'assumptions': {
            'pricing': 'External book and scenario inputs are required. Explicit Polymarket auto '
                       'calibration may seed an assumed spread from the initial token print.',
            'model': 'Kalshi uses external fair probability; weather uses observation/expiry bounds. '
                     'Polymarket auto calibration assumes spot=102000, strike=100000, volatility=0.60.',
            'settlement': 'Provided independent binary payout, or assumed win only in explicit '
                          'Polymarket auto calibration. NOAA observations cannot create executions.',
            'selection': 'External scenarios select contracts. Only explicit Polymarket calibration '
                         'selects the primary contract by normalized count with an ID tie-break.',
            'time_bounds': 'External scenario bounds are required. Only in Polymarket calibration: '
                           'first token timestamp seeds the book. Decision is 1ns later; '
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
        'by_venue': by_venue,
        'missing_venues': [venue for venue, result in by_venue.items() if result['status'] == 'NO_TAPES'],
        'data_qualification': {
            'fresh_harvest_verified': False,
            'nonoverlapping_captures': bool(unique) and not summary['duplicate_tape_count'] and not summary['rejected_tapes'],
            'official_settlement_verified': False,
            'venue_coverage_complete': all(result['status'] == 'EVALUATED' for result in by_venue.values()),
            'scope': 'Offline replay of existing captures; neither a new harvest nor venue profit certification.',
        },
        'duplicate_capture_groups': [
            {'venue': venue, 'fixture_sha256': digest, 'tape_paths': paths}
            for (venue, digest), paths in sorted(capture_groups.items()) if len(paths) > 1
        ],
        'results': results,
    }


def print_scorecard(report: dict) -> None:
    s = report['summary']
    u = report['unique_summary']
    split = u['waterfall']
    rows = [
        ('Status', report['status']),
        ('Tapes evaluated / expected', f"{s['total_tapes_evaluated']} / {report['expected_tape_count'] if report['expected_tape_count'] is not None else 'any'}"),
        ('Trades parsed / expected', f"{s['total_trades_parsed']:,} / {report['expected_trade_count'] if report['expected_trade_count'] is not None else 'any'}"),
        ('Markets identified across venues', s['total_markets_evaluated']),
        ('Weather observations parsed / evaluated', f"{s['total_observations_parsed']} / {s['total_observations_evaluated']}"),
        ('Replayed / seed / excluded trades', f"{s['total_trades_replayed']:,} / {s['total_initialization_trades']:,} / {s['total_trades_excluded']:,}"),
        ('Admitted / abstained / rejected', f"{s['admitted_executions']} / {s['abstained_executions']} / {s['rejected_tapes']}"),
        ('Unique / duplicate captures', f"{s['unique_tape_count']} / {s['duplicate_tape_count']}"),
        ('Total unique trades', u['total_unique_trades']),
        ('Total unique observations', u['total_unique_observations']),
        ('Unique fill events / deployed volume', f"{u['maker_fill_count']} / {u['volume_deployed']} lots"),
        ('Unique deployed capital (cents)', u['deployed_cents']),
        ('Unique net PnL (scenario cents)', u['net_pnl_cents']),
        ('SCMA 87% (cents)', split['scma_cents']),
        ('FAEP 3% (cents)', split['faep_cents']),
        ('CFCP 10% + residual (cents)', split['cfcp_cents']),
        ('ADR-008 exact-cent conservation', 'PASS' if s['exact_cent_conservation'] else 'FAIL'),
    ]
    print('=' * 76)
    print(' MULTI-VENUE AUTHENTIC REPLAY - ' + report['replay_mode'])
    print(' Financial totals count each capture once; missing scenarios abstain.')
    print('-' * 76)
    for label, value in rows:
        print(f' {label:<39} {value}')
    for venue, result in report['by_venue'].items():
        print(f" {venue:<39} {result['status']} ({result['tape_count']} tapes)")
    print('=' * 76)


def render_markdown(report: dict) -> str:
    s, u = report['summary'], report['unique_summary']
    split = u['waterfall']
    venue_rows = '\n'.join(
        f"| {venue} | {result['status']} | {result['tape_count']} | {result['market_count']} | "
        f"{result['trade_print_count']} | {result['observation_count']} | {result['admitted']} / {result['abstained']} |"
        for venue, result in report['by_venue'].items())
    return f"""# PDEUE WP-8Q Multi-Category Replay Scorecard

Source: `backend/reports/authentic_batch_replay_scorecard.json`.
Mode: **{report['replay_mode']}**.
Financial results use provided scenarios, or explicitly opted-in Polymarket
calibration assumptions. Missing external scenarios abstain. NOAA temperatures
remain observations and never create trade prices, lots, or maker fills.

| Venue | Coverage | Files | Markets identified | Trade prints | Observations | Admitted / abstained |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{venue_rows}

| Metric | Unique-capture result |
| --- | ---: |
| Total unique trades | {u['total_unique_trades']} |
| Markets with independent scenarios | {s['markets_with_independent_scenarios']} |
| Total unique weather observations | {u['total_unique_observations']} |
| Post-decision token prints replayed | {u['replayed_trade_count']} |
| Initialization prints excluded | {u['initialization_trade_count']} |
| Maker fill events | {u['maker_fill_count']} |
| Filled volume (lots) | {u['volume_deployed']} |
| Deployed capital (cents) | {u['deployed_cents']} |
| Settlement payout (scenario cents) | {u['payout_cents']} |
| Fees (cents) | {u['fee_cents']} |
| Net realized PnL (scenario cents) | {u['net_pnl_cents']} |

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

Kalshi uses explicit external fair probability, binary payout, book, capital, and
point-in-time bounds. Strategy D SELL flow at or below the resting bid clears queue
before filling at that bid; BUY flow cannot fill it. Independent settlement inputs
do not alter prior fills. Kalshi does not accept synthetic auto-scenarios.

Weather bounds must match the selected strike's station and expiry. Brackets are
half-open [lower, upper); post-expiry or late-published observations are excluded.
Even qualified observation evaluation abstains with NO_EXECUTION_TAPE when no
execution data exists. These are not official station settlement certifications.

Explicit Polymarket calibration can seed a spread from the first token timestamp,
excluding that timestamp from execution. Its spread, five-lot queue, model, and
winning payout remain assumptions. It is disabled by default in the batch CLI.

The corrected harvester uses market-filtered offset pagination, exact condition
and YES-token verification, and cross-market hash uniqueness before writing files.
Fresh harvesting has not been verified for this offline report. Existing duplicate
captures remain preserved; their filename markets do not establish their contents'
settled-market provenance. Official settlement is not available for this simulation.
Missing venue datasets: {', '.join(report['missing_venues']) or 'none'}.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tape-dir', type=Path, help='Legacy single Polymarket directory')
    parser.add_argument('--venues-root', type=Path, default=DEFAULT_VENUES_ROOT)
    parser.add_argument('--kalshi-dir', type=Path)
    parser.add_argument('--weather-dir', type=Path, action='append')
    parser.add_argument('--scenario-manifest', type=Path,
                        help='JSON venue -> filename -> complete scenario (or scenario/queue_ahead/strategy_d object)')
    parser.add_argument('--auto-scenario', action='store_true',
                        help='Explicit Polymarket calibration only; Kalshi and weather still need external bounds')
    parser.add_argument('--output', type=Path, default=DEFAULT_REPORT)
    parser.add_argument('--markdown-output', type=Path,
                        help='Markdown scorecard; defaults to reports/LATEST_REPLAY_SCORECARD.md for the default JSON output')
    parser.add_argument('--expected-tapes', type=int)
    parser.add_argument('--expected-trades', type=int)
    args = parser.parse_args()
    if any(value is not None and value <= 0 for value in (args.expected_tapes, args.expected_trades)):
        parser.error('expected counts must be positive')
    venue_dirs = {'polymarket': args.tape_dir} if args.tape_dir else {
        'polymarket': args.venues_root / 'polymarket', 'kalshi': args.venues_root / 'kalshi',
        'weather': [args.venues_root / 'weather', args.venues_root / 'noaa', args.venues_root.parent / 'noaa'],
    }
    if args.kalshi_dir:
        venue_dirs['kalshi'] = args.kalshi_dir
    if args.weather_dir:
        venue_dirs['weather'] = args.weather_dir
    scenarios = json.loads(args.scenario_manifest.read_text()) if args.scenario_manifest else None
    report = run_batch(expected_tapes=args.expected_tapes, expected_trades=args.expected_trades,
                       venue_dirs=venue_dirs, scenario_manifest=scenarios, auto_scenario=args.auto_scenario)
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
