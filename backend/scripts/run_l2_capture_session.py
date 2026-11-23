"""Continuous read-only dual-venue OBSERVED_L2 capture session runner (Gate G1 evidence)."""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.adapters.live_l2_tape_recorder import (
    ReadOnlyL2TapeRecorder,
    discover_liquid_kalshi_tickers,
    discover_liquid_polymarket_tokens,
    verify_tape_manifest,
)


def run_capture_session(
    output_dir: Path,
    *,
    kalshi_tickers: Optional[List[str]] = None,
    poly_tokens: Optional[List[str]] = None,
    kalshi_count: int = 2,
    poly_count: int = 2,
    duration_seconds: float = 60.0,
    interval_seconds: float = 5.0,
    http_client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Poll multiple Kalshi & Polymarket contracts read-only and seal a verified OBSERVED_L2 manifest."""
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=15.0)
    recorder = ReadOnlyL2TapeRecorder(output_dir, http_client=client, require_non_empty_book=True)

    k_list = list(kalshi_tickers) if kalshi_tickers is not None else discover_liquid_kalshi_tickers(http_client=client, limit=kalshi_count)
    p_list = list(poly_tokens) if poly_tokens is not None else discover_liquid_polymarket_tokens(http_client=client, limit=poly_count)

    errors: List[str] = []
    cycles = 0
    deadline = time.monotonic() + max(0.0, float(duration_seconds))

    try:
        while True:
            cycles += 1
            for ticker in k_list:
                try:
                    recorder.capture_kalshi_snapshot(ticker)
                except Exception as exc:
                    errors.append(f"KALSHI:{ticker}:{exc}")
            for tok in p_list:
                try:
                    recorder.capture_polymarket_snapshot(tok)
                except Exception as exc:
                    errors.append(f"POLYMARKET:{tok[:16]}:{exc}")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(float(interval_seconds), remaining))
    except KeyboardInterrupt:
        pass
    finally:
        if owns_client:
            client.close()

    manifest = recorder.finalize_manifest()
    verified = verify_tape_manifest(recorder.manifest_path, require_non_empty_book=True)
    return {
        "output_dir": str(output_dir),
        "cycles": cycles,
        "kalshi_tickers": k_list,
        "poly_tokens": p_list,
        "snapshot_count": verified["snapshot_count"],
        "tape_manifest_sha256": verified["tape_manifest_sha256"],
        "errors_count": len(errors),
        "errors_sample": errors[:5],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--duration-seconds", type=float, default=30.0)
    p.add_argument("--interval-seconds", type=float, default=5.0)
    p.add_argument("--kalshi-count", type=int, default=2)
    p.add_argument("--poly-count", type=int, default=2)
    p.add_argument("--output-dir", type=Path, default=None)
    args = p.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.output_dir or (Path(__file__).resolve().parents[2] / "data" / "observed_l2" / f"session_{ts}")
    summary = run_capture_session(
        out_dir,
        kalshi_count=args.kalshi_count,
        poly_count=args.poly_count,
        duration_seconds=args.duration_seconds,
        interval_seconds=args.interval_seconds,
    )
    print(
        f"[VERIFIED L2 SESSION] cycles={summary['cycles']} | snapshots={summary['snapshot_count']} "
        f"| errors={summary['errors_count']} | sha256={summary['tape_manifest_sha256']} | dir={summary['output_dir']}"
    )


if __name__ == "__main__":
    main()
