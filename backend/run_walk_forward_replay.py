#!/usr/bin/env python3
"""Run offline static or captured Polymarket walk-forward replay."""
import argparse
from dataclasses import fields
import json
from pathlib import Path

from app.adapters.authentic_polymarket_tape_loader import DEFAULT_TAPE
from app.domain.walk_forward_replay_harness import DEFAULT_FIXTURE, ReplayScenario, WalkForwardReplayHarness


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('static', 'authentic'), default='static')
    parser.add_argument('--fixture', type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument('--tape', type=Path, default=DEFAULT_TAPE)
    parser.add_argument('--scenario', type=Path,
                        help='JSON ReplayScenario with independent pre-tape inputs and settlement')
    args = parser.parse_args()
    scenario = None
    if args.scenario:
        values = json.loads(args.scenario.read_text())
        if args.mode == 'authentic' and (
                not isinstance(values, dict) or set(values) != {field.name for field in fields(ReplayScenario)}):
            parser.error('authentic mode requires a complete ReplayScenario; synthetic defaults are prohibited')
        if 'bid_depth' in values:
            values['bid_depth'] = {int(price): depth for price, depth in values['bid_depth'].items()}
        scenario = ReplayScenario(**values)
    harness = WalkForwardReplayHarness(scenario)
    result = harness.run_authentic(args.tape) if args.mode == 'authentic' else harness.run(args.fixture)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
