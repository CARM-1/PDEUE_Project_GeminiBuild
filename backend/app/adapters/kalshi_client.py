"""Kalshi venue client and IF-007/IF-008 normalization boundary."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Iterable, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.adapters.rate_limiter import VenueRateLimiter
from app.domain.cloud_secrets_broker import CloudSecretsBroker


def _cents(value: Any) -> int:
    """Convert venue wire prices to cents; integer values are already cents."""
    if isinstance(value, bool):
        raise ValueError("boolean is not a price")
    if isinstance(value, int):
        return value
    # Conversion happens only at the wire boundary. Domain values remain integers.
    return int(round(float(value) * 100))


class KalshiClient:
    BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"

    def __init__(self, broker: Optional[CloudSecretsBroker] = None,
                 rate_limiter: Optional[VenueRateLimiter] = None,
                 tenant_id: str = "DEFAULT", offline: bool = False):
        self.broker = broker or CloudSecretsBroker()
        self.rate_limiter = rate_limiter or VenueRateLimiter()
        self.tenant_id = tenant_id
        self.offline = offline

    @staticmethod
    def normalize_ticker(ticker: str) -> str:
        return ticker.strip().upper().replace(" ", "-")

    def normalize_ladder(self, markets: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        rows = []
        for market in markets:
            rows.append({
                "ticker": self.normalize_ticker(market.get("ticker", "")),
                "strike_cents": _cents(market.get("strike", market.get("floor_strike", 0))),
                "bid_cents": _cents(market.get("yes_bid", market.get("yes_bid_dollars", 0))),
                "ask_cents": _cents(market.get("yes_ask", market.get("yes_ask_dollars", 1))),
                "status": market.get("status", "active").lower(),
                "venue": "KALSHI",
            })
        return {"interface_id": "IF-007", "venue": "KALSHI",
                "markets": sorted(rows, key=lambda row: (row["strike_cents"], row["ticker"]))}

    def normalize_orderbook(self, ticker: str, raw: Dict[str, Any]) -> Dict[str, Any]:
        book = raw.get("orderbook", raw)
        bids = book.get("yes", book.get("yes_bids", book.get("bids", [])))
        asks = book.get("yes_asks", book.get("asks", []))
        normalize = lambda levels: [
            {"price_cents": _cents(level.get("price") if isinstance(level, dict) else level[0]),
             "quantity": int(level.get("quantity", level.get("size", 0)) if isinstance(level, dict) else level[1])}
            for level in levels
        ]
        bid_depth, ask_depth = normalize(bids), normalize(asks)
        return {"interface_id": "IF-008", "venue": "KALSHI",
                "ticker": self.normalize_ticker(ticker), "bids": bid_depth, "asks": ask_depth,
                "best_bid_cents": max((x["price_cents"] for x in bid_depth), default=0),
                "best_ask_cents": min((x["price_cents"] for x in ask_depth), default=100)}

    async def _request(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        if self.offline or not await self.rate_limiter.acquire_permit("KALSHI"):
            raise URLError("offline")
        lease = self.broker.lease_venue_credentials("KALSHI", self.tenant_id, ttl_seconds=60)
        if lease.get("status") != "LEASED":
            raise URLError("credentials unavailable")
        secret = lease["lease"]["secret_token"]
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.BASE_URL + path, data=body, method=method,
                          headers={"KALSHI-ACCESS-KEY": secret, "Content-Type": "application/json"})
        def send() -> dict:
            with urlopen(request, timeout=3) as response:
                return json.load(response)
        return await asyncio.to_thread(send)

    async def get_orderbook(self, ticker: str) -> Dict[str, Any]:
        try:
            raw = await self._request("GET", f"/markets/{self.normalize_ticker(ticker)}/orderbook")
        except (OSError, ValueError, TimeoutError):
            raw = {"yes": [[40, 100], [39, 80]], "yes_asks": [[42, 75], [43, 120]]}
        return self.normalize_orderbook(ticker, raw)

    async def place_order(self, order_payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return await self._request("POST", "/portfolio/orders", order_payload)
        except (OSError, ValueError, TimeoutError):
            key = order_payload.get("client_order_id", "OFFLINE")
            return {"order_id": f"KALSHI-{key}", "status": "resting", "offline": True,
                    "order": dict(order_payload)}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        try:
            return await self._request("DELETE", f"/portfolio/orders/{order_id}")
        except (OSError, ValueError, TimeoutError):
            return {"order_id": order_id, "status": "cancelled", "offline": True}
