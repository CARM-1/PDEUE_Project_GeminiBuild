"""CLI to record read-only public Kalshi / Polymarket L2 order-book snapshots into a SHA-256 sealed tape."""
import argparse
import time
from pathlib import Path
from app.adapters.live_l2_tape_recorder import (
    ReadOnlyL2TapeRecorder,
    discover_liquid_kalshi_tickers,
    discover_liquid_polymarket_tokens,
    verify_tape_manifest,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--venue", choices=["KALSHI", "POLYMARKET"], required=True)
    p.add_argument("--ticker", help="Kalshi market ticker or Polymarket token_id (omit to auto-discover)")
    p.add_argument("--snapshots", type=int, default=3)
    p.add_argument("--interval-seconds", type=float, default=1.0)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()

    ticker = args.ticker
    if not ticker:
        discovered = (
            discover_liquid_kalshi_tickers(limit=1)
            if args.venue == "KALSHI"
            else discover_liquid_polymarket_tokens(limit=1)
        )
        if not discovered:
            raise SystemExit(f"No active liquid {args.venue} contracts discovered")
        ticker = discovered[0]

    rec = ReadOnlyL2TapeRecorder(args.output_dir)
    try:
        for i in range(args.snapshots):
            if args.venue == "KALSHI":
                rec.capture_kalshi_snapshot(ticker)
            else:
                rec.capture_polymarket_snapshot(ticker)
            if i + 1 < args.snapshots:
                time.sleep(args.interval_seconds)
        manifest = rec.finalize_manifest()
        verify_tape_manifest(rec.manifest_path)
        print(f"[VERIFIED OBSERVED_L2] {args.venue}:{ticker} | {manifest['snapshot_count']} snapshots | sha256={manifest['tape_manifest_sha256']}")
    finally:
        rec.close()


if __name__ == "__main__":
    main()
