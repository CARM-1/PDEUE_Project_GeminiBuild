"""Fail-closed 24/7 read-only OBSERVED_L2 public market-tape collector for AWS Lightsail.

Polls public read-only Kalshi and Polymarket order-book endpoints (zero private API
credentials), appends verified integer-cent OBSERVED_L2 JSONL snapshots under
`/var/lib/pdeue/tapes`, maintains a SHA-256 tape manifest, and emits structured JSON
heartbeats without crashing on transient venue timeouts, HTTP 429 rate limits, or 5xx errors.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.adapters.live_l2_tape_recorder import (
    ReadOnlyL2TapeRecorder,
    discover_liquid_kalshi_tickers,
    discover_liquid_polymarket_tokens,
)

ALLOWED_PAPER_MODES = frozenset({"paper", "observation"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def assert_fail_closed_paper_mode(env: Optional[Dict[str, str]] = None) -> str:
    """Refuse to run if live trading is enabled or venue mode is outside paper/observation."""
    source = env if env is not None else os.environ
    venue_mode = str(source.get("PDEUE_VENUE_MODE", "paper")).strip().lower() or "paper"
    live_flag = str(source.get("PDEUE_LIVE_TRADING_ENABLED", "false")).strip().lower() or "false"
    if venue_mode not in ALLOWED_PAPER_MODES:
        raise RuntimeError(
            f"FAIL-CLOSED: OBSERVED_L2 collector refuses PDEUE_VENUE_MODE={venue_mode!r}; "
            f"must be one of {sorted(ALLOWED_PAPER_MODES)}."
        )
    if live_flag not in {"false", "0", "no"}:
        raise RuntimeError(
            f"FAIL-CLOSED: OBSERVED_L2 collector refuses PDEUE_LIVE_TRADING_ENABLED={live_flag!r}; "
            "Gate G1 paper/observation isolation requires PDEUE_LIVE_TRADING_ENABLED=false."
        )
    return venue_mode


class ObservedL2Collector:
    """Resilient, strictly read-only OBSERVED_L2 snapshot collector for unattended paper nodes."""

    def __init__(
        self,
        tape_root: Path,
        *,
        kalshi_tickers: Optional[List[str]] = None,
        poly_tokens: Optional[List[str]] = None,
        kalshi_count: int = 2,
        poly_count: int = 2,
        interval_seconds: float = 60.0,
        max_backoff_seconds: float = 300.0,
        rediscover_every_cycles: int = 30,
        request_timeout_seconds: float = 10.0,
        http_client: Optional[httpx.Client] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        log_fn: Callable[[str], None] = print,
        session_id: Optional[str] = None,
    ) -> None:
        self.venue_mode = assert_fail_closed_paper_mode()
        self.tape_root = Path(tape_root)
        self.tape_root.mkdir(parents=True, exist_ok=True)

        stamp = session_id or datetime.now(timezone.utc).strftime("session_%Y%m%dT%H%M%SZ")
        session_dir = self.tape_root / stamp
        if session_dir.exists() and (session_dir / "tape.jsonl").exists():
            stamp = f"{stamp}_{int(time.time() * 1_000_000) % 1_000_000:06d}"
            session_dir = self.tape_root / stamp
        self.session_dir = session_dir
        self.heartbeat_path = self.tape_root / "collector_heartbeat.json"

        self._owns_client = http_client is None
        self.client = http_client or httpx.Client(
            timeout=request_timeout_seconds,
            headers={"User-Agent": "PDEUE-ObservedL2-Collector/1.0 (read-only)"},
        )
        self.recorder = ReadOnlyL2TapeRecorder(
            self.session_dir,
            http_client=self.client,
            require_non_empty_book=True,
        )

        self._pinned_kalshi = list(kalshi_tickers) if kalshi_tickers is not None else None
        self._pinned_poly = list(poly_tokens) if poly_tokens is not None else None
        self.kalshi_tickers: List[str] = list(kalshi_tickers) if kalshi_tickers is not None else []
        self.poly_tokens: List[str] = list(poly_tokens) if poly_tokens is not None else []
        self.kalshi_count = max(0, int(kalshi_count))
        self.poly_count = max(0, int(poly_count))
        self.interval_seconds = max(0.0, float(interval_seconds))
        self.max_backoff_seconds = max(self.interval_seconds, float(max_backoff_seconds))
        self.rediscover_every_cycles = max(1, int(rediscover_every_cycles))
        self._sleep = sleep_fn
        self._log = log_fn

        self.cycles = 0
        self.snapshots_total = 0
        self.errors_total = 0
        self.consecutive_errors = 0
        self.last_error: Optional[str] = None
        self._stop_requested = False
        self._force_rediscover_kalshi = False
        self._force_rediscover_poly = False
        self._dead_poly_tokens: set[str] = set()

    def request_stop(self) -> None:
        self._stop_requested = True

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _refresh_targets_if_needed(self, errors: List[str]) -> bool:
        rate_limited = False
        periodic_refresh = self.cycles == 1 or (self.cycles % self.rediscover_every_cycles == 0)

        refresh_kalshi = (
            self._pinned_kalshi is None
            and self.kalshi_count > 0
            and (
                periodic_refresh
                or self._force_rediscover_kalshi
                or len(self.kalshi_tickers) < self.kalshi_count
            )
        )
        refresh_poly = (
            self._pinned_poly is None
            and self.poly_count > 0
            and (
                periodic_refresh
                or self._force_rediscover_poly
                or len(self.poly_tokens) < self.poly_count
            )
        )

        if refresh_kalshi:
            try:
                discovered = discover_liquid_kalshi_tickers(
                    http_client=self.client,
                    limit=self.kalshi_count,
                )
                if discovered:
                    self.kalshi_tickers = discovered
                    self._force_rediscover_kalshi = False
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    rate_limited = True
                errors.append(f"DISCOVER:KALSHI:HTTP_{exc.response.status_code}")
            except Exception as exc:
                errors.append(f"DISCOVER:KALSHI:{type(exc).__name__}:{exc}")

        if refresh_poly:
            if periodic_refresh and len(self._dead_poly_tokens) > 100:
                self._dead_poly_tokens.clear()
            try:
                discovered = discover_liquid_polymarket_tokens(
                    http_client=self.client,
                    limit=self.poly_count,
                    verify_orderbook=True,
                    require_non_empty_book=True,
                    exclude_tokens=self._dead_poly_tokens,
                )
                if discovered:
                    self.poly_tokens = discovered
                    self._force_rediscover_poly = False
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    rate_limited = True
                errors.append(f"DISCOVER:POLYMARKET:HTTP_{exc.response.status_code}")
            except Exception as exc:
                errors.append(f"DISCOVER:POLYMARKET:{type(exc).__name__}:{exc}")

        return rate_limited

    def _write_heartbeat(self, heartbeat: Dict[str, Any]) -> None:
        payload = json.dumps(heartbeat, sort_keys=True)
        tmp_path = self.heartbeat_path.with_suffix(".json.tmp")
        tmp_path.write_text(payload + "\n", encoding="utf-8")
        tmp_path.replace(self.heartbeat_path)
        self._log(payload)

    def collect_once(self) -> Dict[str, Any]:
        """Execute one resilient read-only poll cycle across configured venues."""
        self.cycles += 1
        cycle_errors: List[str] = []
        cycle_snapshots = 0
        rate_limited = self._refresh_targets_if_needed(cycle_errors)

        for ticker in list(self.kalshi_tickers):
            try:
                self.recorder.capture_kalshi_snapshot(ticker)
                cycle_snapshots += 1
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    rate_limited = True
                elif exc.response.status_code == 404 and self._pinned_kalshi is None:
                    self.kalshi_tickers = [t for t in self.kalshi_tickers if t != ticker]
                    self._force_rediscover_kalshi = True
                cycle_errors.append(f"KALSHI:{ticker}:HTTP_{exc.response.status_code}")
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                cycle_errors.append(f"KALSHI:{ticker}:{type(exc).__name__}")
            except Exception as exc:
                cycle_errors.append(f"KALSHI:{ticker}:{type(exc).__name__}:{exc}")

        for token_id in list(self.poly_tokens):
            try:
                self.recorder.capture_polymarket_snapshot(token_id)
                cycle_snapshots += 1
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    rate_limited = True
                elif exc.response.status_code == 404 and self._pinned_poly is None:
                    self._dead_poly_tokens.add(token_id)
                    self.poly_tokens = [t for t in self.poly_tokens if t != token_id]
                    self._force_rediscover_poly = True
                cycle_errors.append(f"POLYMARKET:{token_id[:16]}:HTTP_{exc.response.status_code}")
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                cycle_errors.append(f"POLYMARKET:{token_id[:16]}:{type(exc).__name__}")
            except Exception as exc:
                cycle_errors.append(f"POLYMARKET:{token_id[:16]}:{type(exc).__name__}:{exc}")

        self.snapshots_total += cycle_snapshots
        self.errors_total += len(cycle_errors)

        if cycle_snapshots > 0:
            self.consecutive_errors = 0
            manifest = self.recorder.finalize_manifest()
            manifest_sha = manifest["tape_manifest_sha256"]
        else:
            if cycle_errors:
                self.consecutive_errors += 1
            manifest_sha = None

        if cycle_errors:
            self.last_error = cycle_errors[-1]

        status = "HEALTHY" if cycle_snapshots > 0 and not cycle_errors else (
            "DEGRADED" if (cycle_snapshots > 0 or not cycle_errors) else "WAITING_ON_VENUE"
        )
        heartbeat = {
            "event": "OBSERVED_L2_HEARTBEAT",
            "timestamp_utc": _utc_now_iso(),
            "status": status,
            "venue_mode": self.venue_mode,
            "live_trading_enabled": False,
            "data_provenance": "OBSERVED_L2",
            "synthetic_fills_present": False,
            "cycle": self.cycles,
            "cycle_snapshots": cycle_snapshots,
            "snapshots_total": self.snapshots_total,
            "cycle_errors_count": len(cycle_errors),
            "errors_total": self.errors_total,
            "consecutive_errors": self.consecutive_errors,
            "rate_limited": rate_limited,
            "last_error": self.last_error,
            "session_dir": str(self.session_dir),
            "tape_path": str(self.recorder.tape_path),
            "tape_manifest_sha256": manifest_sha,
        }
        self._write_heartbeat(heartbeat)
        return heartbeat

    def _next_sleep_seconds(self, heartbeat: Dict[str, Any]) -> float:
        if self.interval_seconds <= 0:
            return 0.0
        if heartbeat.get("rate_limited") or self.consecutive_errors > 0:
            multiplier = min(2 ** min(self.consecutive_errors, 4), 8)
            return min(self.interval_seconds * multiplier, self.max_backoff_seconds)
        return self.interval_seconds

    def run(self, *, max_cycles: Optional[int] = None) -> Dict[str, Any]:
        """Run the collector loop until max_cycles is reached or a stop signal arrives."""
        last_heartbeat: Dict[str, Any] = {}
        try:
            while not self._stop_requested:
                last_heartbeat = self.collect_once()
                if max_cycles is not None and self.cycles >= max_cycles:
                    break
                delay = self._next_sleep_seconds(last_heartbeat)
                if delay > 0 and not self._stop_requested:
                    self._sleep(delay)
        finally:
            self.close()
        return last_heartbeat


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tape-dir",
        type=Path,
        default=Path(os.getenv("PDEUE_TAPE_DIR", "/var/lib/pdeue/tapes")),
        help="Persistent directory where OBSERVED_L2 JSONL tapes and manifests are written.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=float(os.getenv("PDEUE_L2_POLL_INTERVAL_SECONDS", "60")),
        help="Respectful polling interval in seconds between public read-only snapshots.",
    )
    parser.add_argument(
        "--kalshi-count",
        type=int,
        default=int(os.getenv("PDEUE_L2_KALSHI_COUNT", "2")),
        help="Number of liquid Kalshi markets to discover and observe.",
    )
    parser.add_argument(
        "--poly-count",
        type=int,
        default=int(os.getenv("PDEUE_L2_POLY_COUNT", "2")),
        help="Number of liquid Polymarket contracts to discover and observe.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Optional cycle limit (omit for continuous 24/7 observation).",
    )
    args = parser.parse_args(argv)

    collector = ObservedL2Collector(
        args.tape_dir,
        kalshi_count=args.kalshi_count,
        poly_count=args.poly_count,
        interval_seconds=args.interval_seconds,
    )

    def _handle_signal(_signum: int, _frame: Any) -> None:
        collector.request_stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    collector.run(max_cycles=args.max_cycles)
    return 0


if __name__ == "__main__":
    sys.exit(main())
