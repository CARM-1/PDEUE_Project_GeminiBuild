"""Polymarket CLOB sandbox adapter with encapsulated typed-order signing."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Callable, Mapping, Optional

import httpx

from app.clients.kalshi_client import KalshiClient
from app.services.credential_broker import TenantCredentialLease


OrderSigner = Callable[[Mapping[str, Any], TenantCredentialLease], str]


class PolymarketClient(KalshiClient):
    # The URL remains injectable so deployments can select their approved CLOB sandbox.
    BASE_URL = "https://clob.polymarket.com"

    def __init__(self, *args: Any, order_signer: Optional[OrderSigner] = None, **kwargs: Any) -> None:
        kwargs.setdefault("base_url", self.BASE_URL)
        super().__init__(*args, **kwargs)
        self.order_signer = order_signer or self._sign_eip712_order

    @staticmethod
    def _sign_eip712_order(order: Mapping[str, Any], lease: TenantCredentialLease) -> str:
        """Encapsulate deterministic EIP-712 signing behind an injectable boundary.

        Production supplies a hardware-wallet/EIP-712 signer.  This default creates
        a domain-separated digest suitable for hermetic sandbox tests without adding
        or persisting wallet dependencies.
        """
        canonical = json.dumps(order, separators=(",", ":"), sort_keys=True).encode()
        return "0x" + hmac.new(
            lease.api_secret.encode(), b"PDEUE-POLYMARKET-EIP712\0" + canonical,
            hashlib.sha256,
        ).hexdigest()

    async def _request(self, method: str, path: str, payload: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        lease = self.credential_broker.acquire_lease(self.tenant_id, "POLYMARKET", 60)
        try:
            for attempt in range(self.max_retries + 1):
                if not await self.rate_limiter.acquire_permit("POLYMARKET"):
                    raise TimeoutError("Polymarket rate-limit permit timed out")
                body = self._body(payload)
                headers = {
                    "POLY-API-KEY": lease.api_key,
                    "POLY-SIGNATURE": hmac.new(lease.api_secret.encode(), body, hashlib.sha256).hexdigest(),
                    "Content-Type": "application/json",
                }
                owns_client = self._http_client is None
                client = self._http_client or httpx.AsyncClient(timeout=10)
                try:
                    response = await client.request(method, self.base_url + path, content=body or None, headers=headers)
                finally:
                    if owns_client:
                        await client.aclose()
                if response.status_code != 429:
                    response.raise_for_status()
                    self.rate_limiter.reset_backoff("POLYMARKET")
                    return response.json() if response.content else {}
                if attempt == self.max_retries:
                    response.raise_for_status()
                await self._sleep(self.rate_limiter.compute_backoff("POLYMARKET"))
            raise RuntimeError("unreachable")
        finally:
            self.credential_broker.revoke_lease(lease.lease_id)

    async def get_sampling_markets(self, **params: Any) -> dict[str, Any]:
        query = str(httpx.QueryParams(params))
        return await self._request("GET", "/sampling-markets" + (f"?{query}" if query else ""))

    async def get_order_book(self, token_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/book?token_id={token_id}")

    async def create_order(self, order: Optional[Mapping[str, Any]] = None, **fields: Any) -> dict[str, Any]:
        payload = dict(order or {})
        payload.update(fields)
        for name in ("price_cents", "size", "fee_cents"):
            if name in payload and (isinstance(payload[name], bool) or not isinstance(payload[name], int)):
                raise TypeError(f"{name} must be an integer")
        lease = self.credential_broker.acquire_lease(self.tenant_id, "POLYMARKET", 60)
        try:
            payload["signature"] = self.order_signer(payload, lease)
        finally:
            self.credential_broker.revoke_lease(lease.lease_id)
        return await self._request("POST", "/order", payload)

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/order/{order_id}")

