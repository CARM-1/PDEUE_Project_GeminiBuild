#!/usr/bin/env python3
"""Run the offline WP-8L replay: ./run_walk_forward_replay.py."""
import argparse
import json
from pathlib import Path

from app.domain.walk_forward_replay_harness import DEFAULT_FIXTURE, WalkForwardReplayHarness


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    print(json.dumps(WalkForwardReplayHarness().run(args.fixture), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
