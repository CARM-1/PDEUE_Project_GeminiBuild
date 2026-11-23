"""Read-only, zero-synthetic microstructure & replay evaluator for OBSERVED_L2 tapes (Gate G1)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.adapters.live_l2_tape_recorder import verify_tape_manifest


def evaluate_tape_directory(tape_dir: Path) -> Dict[str, Any]:
    """Verify manifest integrity and summarize observed L2 spreads and depth without synthetic fills."""
    tdir = Path(tape_dir)
    manifest_path = tdir / "tape_manifest.json"
    manifest = verify_tape_manifest(manifest_path, require_non_empty_book=True)
    tape_path = tdir / manifest["tape_file"]

    snapshots: List[Dict[str, Any]] = []
    for line in tape_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            snapshots.append(json.loads(line))

    by_contract: Dict[str, Dict[str, Any]] = {}
    spreads_cents: List[int] = []

    for snap in snapshots:
        key = f"{snap['venue']}:{snap['contract_ticker']}"
        bids = snap.get("bids") or []
        asks = snap.get("asks") or []
        best_bid = bids[0][0] if bids else None
        best_bid_sz = bids[0][1] if bids else 0
        best_ask = asks[0][0] if asks else None
        best_ask_sz = asks[0][1] if asks else 0
        spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
        if spread is not None:
            spreads_cents.append(spread)

        stat = by_contract.setdefault(key, {
            "venue": snap["venue"],
            "contract_ticker": snap["contract_ticker"],
            "snapshots": 0,
            "min_spread_cents": None,
            "max_spread_cents": None,
            "max_best_bid_cents": None,
            "min_best_ask_cents": None,
            "total_top_bid_lots": 0,
            "total_top_ask_lots": 0,
        })
        stat["snapshots"] += 1
        stat["total_top_bid_lots"] += int(best_bid_sz)
        stat["total_top_ask_lots"] += int(best_ask_sz)
        if best_bid is not None:
            stat["max_best_bid_cents"] = best_bid if stat["max_best_bid_cents"] is None else max(stat["max_best_bid_cents"], best_bid)
        if best_ask is not None:
            stat["min_best_ask_cents"] = best_ask if stat["min_best_ask_cents"] is None else min(stat["min_best_ask_cents"], best_ask)
        if spread is not None:
            stat["min_spread_cents"] = spread if stat["min_spread_cents"] is None else min(stat["min_spread_cents"], spread)
            stat["max_spread_cents"] = spread if stat["max_spread_cents"] is None else max(stat["max_spread_cents"], spread)

    return {
        "tape_dir": str(tdir),
        "data_provenance": "OBSERVED_L2",
        "synthetic_fills_present": False,
        "replay_mode": "OBSERVED_L2_MICROSTRUCTURE_AUDIT",
        "tape_manifest_sha256": manifest["tape_manifest_sha256"],
        "snapshot_count": len(snapshots),
        "contracts_observed": len(by_contract),
        "median_or_mean_spread_cents": round(sum(spreads_cents) / len(spreads_cents), 2) if spreads_cents else None,
        "tightest_spread_cents": min(spreads_cents) if spreads_cents else None,
        "widest_spread_cents": max(spreads_cents) if spreads_cents else None,
        "contracts": sorted(by_contract.values(), key=lambda c: (c["venue"], c["contract_ticker"])),
    }


def evaluate_observed_l2_root(root_dir: Path) -> Dict[str, Any]:
    """Evaluate all sealed OBSERVED_L2 sessions under root_dir."""
    rdir = Path(root_dir)
    manifests = sorted(rdir.rglob("tape_manifest.json")) if rdir.exists() else []
    sessions = [evaluate_tape_directory(m.parent) for m in manifests]
    total_snaps = sum(s["snapshot_count"] for s in sessions)
    venues = sorted({c["venue"] for s in sessions for c in s["contracts"]})
    all_tight = [s["tightest_spread_cents"] for s in sessions if s["tightest_spread_cents"] is not None]
    return {
        "root_dir": str(rdir),
        "sessions_verified": len(sessions),
        "total_snapshots": total_snaps,
        "venues_covered": venues,
        "tightest_spread_cents": min(all_tight) if all_tight else None,
        "synthetic_fills_present": False,
        "sessions": sessions,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--observed-l2-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "observed_l2",
    )
    p.add_argument("--json-output", type=Path, default=None)
    args = p.parse_args(argv)

    summary = evaluate_observed_l2_root(args.observed_l2_dir)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"[OBSERVED_L2 AUDIT] sessions={summary['sessions_verified']} | snapshots={summary['total_snapshots']} "
        f"| venues={summary['venues_covered']} | tightest_spread_cents={summary['tightest_spread_cents']} "
        f"| synthetic_fills={summary['synthetic_fills_present']}"
    )
    for sess in summary["sessions"]:
        for c in sess["contracts"]:
            print(
                f"  - {c['venue']}:{c['contract_ticker']} | snaps={c['snapshots']} "
                f"| spread_cents=[{c['min_spread_cents']}..{c['max_spread_cents']}] "
                f"| top_bid_lots={c['total_top_bid_lots']} | top_ask_lots={c['total_top_ask_lots']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
