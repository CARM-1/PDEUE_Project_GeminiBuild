"""Collateral drift monitoring and per-venue request throttling."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Dict


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class CrossVenueManager:
    """Track integer-cent collateral without performing transfers or I/O."""

    VENUES = ("KALSHI", "POLYMARKET")

    def __init__(
        self, kalshi_cents: int = 0, polymarket_cents: int = 0,
        requests_per_second: int = 10, clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        if requests_per_second != 10:
            raise ValueError("RC-B rate limit is fixed at 10 requests/sec")
        self._clock, self._jitter = clock, jitter
        self.rate = requests_per_second
        now = clock()
        self._buckets: Dict[str, _Bucket] = {venue: _Bucket(float(self.rate), now) for venue in self.VENUES}
        self.set_collateral("KALSHI", kalshi_cents)
        self.set_collateral("POLYMARKET", polymarket_cents)

    @staticmethod
    def _validate_cents(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 9_223_372_036_854_775_807:
            raise ValueError("collateral must be a non-negative signed 64-bit integer in cents")
        return value

    @staticmethod
    def _venue(venue: str) -> str:
        normalized = venue.upper()
        if normalized not in CrossVenueManager.VENUES:
            raise ValueError(f"unsupported venue: {venue}")
        return normalized

    def set_collateral(self, venue: str, cents: int) -> None:
        name = self._venue(venue)
        value = self._validate_cents(cents)
        other_name = "POLYMARKET" if name == "KALSHI" else "KALSHI"
        other = getattr(self, f"{other_name.lower()}_cents", 0)
        if value + other > 9_223_372_036_854_775_807:
            raise OverflowError("combined collateral exceeds signed 64-bit integer range")
        setattr(self, f"{name.lower()}_cents", value)

    def collateral_status(self) -> dict[str, int | float | str]:
        total = self.kalshi_cents + self.polymarket_cents
        drift = abs(self.kalshi_cents - self.polymarket_cents) / total if total else 0.0
        return {
            "event": "REBALANCE_REQUIRED" if drift > 0.15 else "BALANCED",
            "kalshi_cents": self.kalshi_cents,
            "polymarket_cents": self.polymarket_cents,
            "total_cents": total,
            "drift_ratio": drift,
        }

    def acquire(self, venue: str) -> dict[str, float | bool]:
        """Consume one token or return a jittered retry delay; never sleeps."""
        name = self._venue(venue)
        now = self._clock()
        bucket = self._buckets[name]
        elapsed = max(0.0, now - bucket.updated_at)
        bucket.tokens = min(float(self.rate), bucket.tokens + elapsed * self.rate)
        bucket.updated_at = now
        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return {"allowed": True, "retry_after_seconds": 0.0}
        base_delay = (1 - bucket.tokens) / self.rate
        return {"allowed": False, "retry_after_seconds": self._jitter(base_delay, base_delay * 1.25)}
