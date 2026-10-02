"""Authenticated asynchronous client for Kalshi's demo exchange."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any, Awaitable, Callable, Mapping, Optional

import httpx

from app.adapters.rate_limiter import VenueRateLimiter
from app.services.credential_broker import CredentialBroker, TenantCredentialLease


Sleep = Callable[[float], Awaitable[None]]


class KalshiClient:
    BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"

    def __init__(
        self,
        credential_broker: CredentialBroker,
        tenant_id: str,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        rate_limiter: Optional[VenueRateLimiter] = None,
        base_url: str = BASE_URL,
        sleep: Sleep = asyncio.sleep,
        max_retries: int = 3,
    ) -> None:
        self.credential_broker = credential_broker
        self.tenant_id = tenant_id
        self.rate_limiter = rate_limiter or VenueRateLimiter()
        self.base_url = base_url.rstrip("/")
        self._http_client = http_client
        self._sleep = sleep
        self.max_retries = max_retries

    @staticmethod
    def _body(payload: Optional[Mapping[str, Any]]) -> bytes:
        return (json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
                if payload is not None else b"")

    @classmethod
    def signing_headers(
        cls, lease: TenantCredentialLease, method: str, path: str,
        payload: Optional[Mapping[str, Any]] = None, timestamp_ms: Optional[int] = None,
    ) -> dict[str, str]:
        """Create Kalshi-compatible timestamp/key/signature request headers."""
        if not lease.is_valid():
            raise PermissionError("credential lease is invalid or expired")
        timestamp = str(timestamp_ms if timestamp_ms is not None else time.time_ns() // 1_000_000)
        message = timestamp.encode() + method.upper().encode() + path.encode() + cls._body(payload)
        signature = hmac.new(lease.api_secret.encode(), message, hashlib.sha256).hexdigest()
        return {
            "KALSHI-ACCESS-KEY": lease.api_key,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "Content-Type": "application/json",
        }

    async def _request(
        self, method: str, path: str, payload: Optional[Mapping[str, Any]] = None
    ) -> dict[str, Any]:
        lease = self.credential_broker.acquire_lease(self.tenant_id, "KALSHI", 60)
        try:
            for attempt in range(self.max_retries + 1):
                if not await self.rate_limiter.acquire_permit("KALSHI"):
                    raise TimeoutError("Kalshi rate-limit permit timed out")
                headers = self.signing_headers(lease, method, path, payload)
                owns_client = self._http_client is None
                client = self._http_client or httpx.AsyncClient(timeout=10)
                try:
                    response = await client.request(
                        method, self.base_url + path, content=self._body(payload) or None,
                        headers=headers,
                    )
                finally:
                    if owns_client:
                        await client.aclose()
                if response.status_code != 429:
                    response.raise_for_status()
                    self.rate_limiter.reset_backoff("KALSHI")
                    return response.json() if response.content else {}
                if attempt == self.max_retries:
                    response.raise_for_status()
                await self._sleep(self.rate_limiter.compute_backoff("KALSHI"))
            raise RuntimeError("unreachable")
        finally:
            self.credential_broker.revoke_lease(lease.lease_id)

    async def get_markets(self, **params: Any) -> dict[str, Any]:
        suffix = str(httpx.QueryParams(params))
        return await self._request("GET", "/markets" + (f"?{suffix}" if suffix else ""))

    async def get_orderbook(self, ticker: str) -> dict[str, Any]:
        return await self._request("GET", f"/markets/{ticker}/orderbook")

    async def place_order(
        self, order: Optional[Mapping[str, Any]] = None, **fields: Any
    ) -> dict[str, Any]:
        payload = dict(order or {})
        payload.update(fields)
        for name in ("yes_price", "no_price", "count"):
            if name in payload and (isinstance(payload[name], bool) or not isinstance(payload[name], int)):
                raise TypeError(f"{name} must be an integer")
        return await self._request("POST", "/portfolio/orders", payload)

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/portfolio/orders/{order_id}")

