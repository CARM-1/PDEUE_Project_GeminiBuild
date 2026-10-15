#!/usr/bin/env python3
"""Run offline static or captured Polymarket walk-forward replay."""
import argparse
from dataclasses import fields
import json
from pathlib import Path

from app.adapters.authentic_polymarket_tape_loader import DEFAULT_TAPE
from app.domain.walk_forward_replay_harness import DEFAULT_FIXTURE, IndependentReplayScenario, ReplayScenario, WalkForwardReplayHarness
from app.adapters.authentic_weather_tape_loader import WeatherReplayScenario


def scenario_from_mapping(values: dict, venue: str):
    scenario_type = (WeatherReplayScenario if venue == 'weather' else IndependentReplayScenario
                     if venue == 'kalshi' or isinstance(values, dict) and 'fair_probability' in values else ReplayScenario)
    if not isinstance(values, dict) or set(values) != {field.name for field in fields(scenario_type)}:
        raise ValueError(f'authentic mode requires a complete {scenario_type.__name__}; synthetic defaults are prohibited')
    values = dict(values)
    if 'bid_depth' in values:
        if not isinstance(values['bid_depth'], dict):
            raise ValueError('bid_depth must be an integer-cent price/depth object')
        converted = {int(price): depth for price, depth in values['bid_depth'].items()}
        if len(converted) != len(values['bid_depth']):
            raise ValueError('duplicate integer-cent book prices')
        values['bid_depth'] = converted
    return scenario_type(**values)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('static', 'authentic'), default='static')
    parser.add_argument('--fixture', type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument('--venue', choices=('polymarket', 'kalshi', 'weather'), default='polymarket')
    parser.add_argument('--tape', type=Path, help='Capture path; defaults to the selected venue directory')
    parser.add_argument('--strategy-d', action='store_true', help='Allow SELL flow at or below the resting limit')
    parser.add_argument('--queue-ahead', type=int, help='Explicit resting queue depth assumption in lots')
    parser.add_argument('--contract-id', help='Select one contract from an authentic multi-contract tape')
    parser.add_argument('--auto-scenario', action='store_true',
                        help='Seed an assumed spread from the initial print, then simulate Strategy D sells with 5 lots ahead')
    parser.add_argument('--scenario', type=Path,
                        help='JSON ReplayScenario with independent pre-tape inputs and settlement')
    args = parser.parse_args()
    if args.mode != 'authentic' and (args.contract_id is not None or args.auto_scenario or
                                    args.venue != 'polymarket' or args.strategy_d or args.queue_ahead is not None):
        parser.error('venue selection and execution options require --mode=authentic')
    scenario = None
    if args.scenario:
        values = json.loads(args.scenario.read_text())
        try:
            scenario = scenario_from_mapping(values, args.venue)
        except ValueError as exc:
            parser.error(str(exc))
        if args.contract_id is not None and args.contract_id != scenario.contract_id:
            parser.error('--contract-id must match the explicit scenario contract_id')
    harness = WalkForwardReplayHarness(scenario, strategy_d=args.strategy_d, queue_ahead=args.queue_ahead)
    result = harness.run_authentic(args.tape, contract_id=args.contract_id,
                                   auto_scenario=args.auto_scenario, venue=args.venue) if args.mode == 'authentic' else harness.run(args.fixture)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
