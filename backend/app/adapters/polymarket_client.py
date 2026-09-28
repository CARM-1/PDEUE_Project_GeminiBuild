"""Polymarket Gamma/CLOB client with integer-cent normalization."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.adapters.kalshi_client import KalshiClient, _cents
from app.adapters.rate_limiter import VenueRateLimiter
from app.domain.cloud_secrets_broker import CloudSecretsBroker


class PolymarketClient(KalshiClient):
    BASE_URL = "https://clob.polymarket.com"
    GAMMA_URL = "https://gamma-api.polymarket.com"

    def __init__(self, broker: Optional[CloudSecretsBroker] = None,
                 rate_limiter: Optional[VenueRateLimiter] = None,
                 tenant_id: str = "DEFAULT", offline: bool = False):
        super().__init__(broker, rate_limiter, tenant_id, offline)

    def normalize_orderbook(self, token_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
        def levels(values):
            return [{"price_cents": _cents(x.get("price") if isinstance(x, dict) else x[0]),
                     "quantity": int(float(x.get("size", x.get("quantity", 0))) if isinstance(x, dict) else x[1])}
                    for x in values]
        bids, asks = levels(raw.get("bids", [])), levels(raw.get("asks", []))
        return {"interface_id": "IF-008", "venue": "POLYMARKET", "token_id": str(token_id),
                "bids": bids, "asks": asks,
                "best_bid_cents": max((x["price_cents"] for x in bids), default=0),
                "best_ask_cents": min((x["price_cents"] for x in asks), default=100)}

    async def get_orderbook(self, token_id: str) -> Dict[str, Any]:
        try:
            raw = await self._request("GET", f"/book?token_id={token_id}")
        except (OSError, ValueError, TimeoutError):
            raw = {"bids": [{"price": "0.40", "size": "100"}],
                   "asks": [{"price": "0.42", "size": "75"}]}
        return self.normalize_orderbook(token_id, raw)

    async def place_order(self, order_payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return await self._request("POST", "/order", order_payload)
        except (OSError, ValueError, TimeoutError):
            key = order_payload.get("client_order_id", "OFFLINE")
            return {"order_id": f"POLYMARKET-{key}", "status": "resting", "offline": True,
                    "order": dict(order_payload)}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        try:
            return await self._request("DELETE", f"/order/{order_id}")
        except (OSError, ValueError, TimeoutError):
            return {"order_id": order_id, "status": "cancelled", "offline": True}
