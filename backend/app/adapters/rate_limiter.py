import time
import random
import asyncio
from typing import Dict, Any, Optional

class TokenBucket:
    def __init__(self, rate: float, capacity: float):
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def refill(self) -> None:
        now = time.monotonic()
        delta = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + delta * self.rate)
        self.last_refill = now

    def consume(self, tokens: float = 1.0) -> bool:
        self.refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    async def acquire(self, tokens: float = 1.0, timeout: float = 5.0) -> bool:
        start = time.monotonic()
        while (time.monotonic() - start) < timeout:
            if self.consume(tokens):
                return True
            await asyncio.sleep(0.02)
        return False

class VenueRateLimiter:
    def __init__(self, default_rates: Optional[Dict[str, Dict[str, float]]] = None):
        configs = default_rates or {
            'KALSHI': {'rate': 10.0, 'capacity': 15.0},
            'POLYMARKET': {'rate': 20.0, 'capacity': 30.0}
        }
        self.buckets: Dict[str, TokenBucket] = {
            v.upper(): TokenBucket(c['rate'], c['capacity'])
            for v, c in configs.items()
        }
        self.backoff_counters: Dict[str, int] = {v.upper(): 0 for v in configs}
        self.warnings_count: int = 0

    def can_proceed(self, venue: str, tokens: float = 1.0) -> bool:
        v = venue.upper()
        bucket = self.buckets.get(v)
        if not bucket:
            return True
        allowed = bucket.consume(tokens)
        if not allowed:
            self.warnings_count += 1
        return allowed

    async def acquire_permit(self, venue: str, tokens: float = 1.0, timeout: float = 5.0) -> bool:
        v = venue.upper()
        bucket = self.buckets.get(v)
        if not bucket:
            return True
        allowed = await bucket.acquire(tokens=tokens, timeout=timeout)
        if not allowed:
            self.warnings_count += 1
        return allowed

    def compute_backoff(self, venue: str, base_delay: float = 0.5, max_delay: float = 10.0) -> float:
        v = venue.upper()
        count = self.backoff_counters.get(v, 0)
        delay = min(max_delay, base_delay * (2.0 ** count))
        jitter = random.uniform(0.0, max(0.01, delay * 0.2))
        self.backoff_counters[v] = count + 1
        self.warnings_count += 1
        return round(delay + jitter, 3)

    def reset_backoff(self, venue: str) -> None:
        self.backoff_counters[venue.upper()] = 0
