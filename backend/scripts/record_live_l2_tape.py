"""CLI to record read-only public Kalshi / Polymarket L2 order-book snapshots into a SHA-256 sealed tape."""
import argparse
import time
from pathlib import Path
from app.adapters.live_l2_tape_recorder import ReadOnlyL2TapeRecorder, verify_tape_manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--venue", choices=["KALSHI", "POLYMARKET"], required=True)
    p.add_argument("--ticker", required=True, help="Kalshi market ticker or Polymarket token_id")
    p.add_argument("--snapshots", type=int, default=3)
    p.add_argument("--interval-seconds", type=float, default=1.0)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()

    rec = ReadOnlyL2TapeRecorder(args.output_dir)
    try:
        for i in range(args.snapshots):
            if args.venue == "KALSHI":
                rec.capture_kalshi_snapshot(args.ticker)
            else:
                rec.capture_polymarket_snapshot(args.ticker)
            if i + 1 < args.snapshots:
                time.sleep(args.interval_seconds)
        manifest = rec.finalize_manifest()
        verify_tape_manifest(rec.manifest_path)
        print(f"[VERIFIED OBSERVED_L2] {manifest['snapshot_count']} snapshots | sha256={manifest['tape_manifest_sha256']}")
    finally:
        rec.close()


if __name__ == "__main__":
    main()
