"""Read-only CLI runner for Brief #01 Parallel Variant Replay Harness & G2A Holdout Adjudicator.

Usage:
    python3 backend/scripts/run_parallel_variant_replay.py --tape-dir <path> --output <json_path>

Invariants:
- Strictly read-only on tape files under `--tape-dir` (never mutates tape or manifest files).
- Fail-closed on manifest tamper, float injection, or parse errors.
- 100% deterministic: two consecutive runs over the same tape produce byte-identical JSON
  and identical SHA-256 `report_sha256` hashes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

# Ensure backend/ is importable whether invoked from repo root or backend/
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.domain.parallel_variant_harness import (  # noqa: E402
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_BOOTSTRAP_SEED,
    run_parallel_variant_replay,
)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tape-dir",
        type=Path,
        required=True,
        help="Path to Schema 2.0.0 tape session directory (or root containing session subdirectories).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination path for deterministic JSON adjudication report.",
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=DEFAULT_BOOTSTRAP_SEED,
        help=f"Deterministic seed for cluster bootstrap (default: {DEFAULT_BOOTSTRAP_SEED}).",
    )
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=DEFAULT_BOOTSTRAP_RESAMPLES,
        help=f"Cluster bootstrap resamples (default: {DEFAULT_BOOTSTRAP_RESAMPLES}).",
    )
    parser.add_argument(
        "--clock-offset-ns",
        type=int,
        default=0,
        help="Optional clock uncertainty offset in nanoseconds added to L (default: 0).",
    )
    parser.add_argument(
        "--replay-git-sha",
        type=str,
        default=None,
        help="Optional explicit replay git SHA override for Cryptographic Freeze Package.",
    )
    parser.add_argument(
        "--verify-determinism",
        action="store_true",
        help="Run replay twice in-process and assert byte-identical JSON & report_sha256 before writing.",
    )
    args = parser.parse_args(argv)

    report = run_parallel_variant_replay(
        args.tape_dir,
        clock_offset_ns=args.clock_offset_ns,
        bootstrap_resamples=args.bootstrap_resamples,
        bootstrap_seed=args.bootstrap_seed,
        replay_git_sha=args.replay_git_sha,
    )
    payload_text = json.dumps(report, indent=2, sort_keys=True) + "\n"

    if args.verify_determinism:
        report_2 = run_parallel_variant_replay(
            args.tape_dir,
            clock_offset_ns=args.clock_offset_ns,
            bootstrap_resamples=args.bootstrap_resamples,
            bootstrap_seed=args.bootstrap_seed,
            replay_git_sha=args.replay_git_sha,
        )
        payload_text_2 = json.dumps(report_2, indent=2, sort_keys=True) + "\n"
        if payload_text != payload_text_2 or report["report_sha256"] != report_2["report_sha256"]:
            raise RuntimeError("DETERMINISM VIOLATION: consecutive replay runs diverged!")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload_text, encoding="utf-8")

    g2a = report["g2a_adjudication"]
    freeze = report["cryptographic_freeze_package"]
    print(
        f"[BRIEF01 REPLAY] verdict={g2a['verdict']} | selected={freeze['selected_variant_id']} "
        f"| holdout_lb_ev_pips={g2a['edge']['lb_ev_pips']} "
        f"| holdout_clusters={g2a['counts']['resolved_event_clusters']} "
        f"| holdout_fills={g2a['counts']['filled_order_episodes_lb']} "
        f"| synthetic_fills={report['synthetic_fills_present']} "
        f"| report_sha256={report['report_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
