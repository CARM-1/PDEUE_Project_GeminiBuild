"""Strategy D passive-maker order routing."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional
from uuid import uuid4

from app.adapters.kalshi_client import KalshiClient
from app.adapters.polymarket_client import PolymarketClient
from app.domain.position_book import PositionBook


class VenueOrderDispatcher:
    """Route integer-cent order intents while preserving capital headroom."""

    MAX_CONCURRENT_ORDERS = 12
    MIN_DRY_POWDER_CENTS = 4_000
    DRY_POWDER_BPS = 4_000

    def __init__(self, clients: Optional[Mapping[str, Any]] = None,
                 position_book: Optional[PositionBook] = None,
                 available_capital_cents: int = 10_000):
        self.clients = {k.upper(): v for k, v in (clients or {
            "KALSHI": KalshiClient(offline=True),
            "POLYMARKET": PolymarketClient(offline=True),
        }).items()}
        self.position_book = position_book or PositionBook()
        self.available_capital_cents = int(available_capital_cents)
        self.routed_orders: Dict[str, Dict[str, Any]] = {}

    async def dispatch(self, candidate: Dict[str, Any], allocated_capital_cents: Optional[int] = None) -> Dict[str, Any]:
        if len(self.routed_orders) >= self.MAX_CONCURRENT_ORDERS:
            return {"status": "REJECTED", "reason": "ORDER_SLOT_LIMIT"}
        venue = str(candidate.get("venue", "KALSHI")).upper()
        if venue not in self.clients:
            return {"status": "REJECTED", "reason": "UNSUPPORTED_VENUE"}
        bid_cents = candidate.get("bid_cents", candidate.get("best_bid_cents"))
        if not isinstance(bid_cents, int) or isinstance(bid_cents, bool):
            raise TypeError("bid_cents must be an integer")
        limit_cents = bid_cents + 1
        if limit_cents >= int(candidate.get("ask_cents", candidate.get("best_ask_cents", 101))):
            return {"status": "REJECTED", "reason": "NO_PASSIVE_INSIDE_PRICE"}
        quantity = int(candidate.get("quantity", 1))
        notional_cents = limit_cents * quantity
        allocation = notional_cents if allocated_capital_cents is None else int(allocated_capital_cents)
        if allocation < notional_cents:
            return {"status": "REJECTED", "reason": "INSUFFICIENT_ALLOCATION"}
        required_reserve = max(self.MIN_DRY_POWDER_CENTS,
                               self.available_capital_cents * self.DRY_POWDER_BPS // 10_000)
        if self.available_capital_cents - notional_cents < required_reserve:
            return {"status": "REJECTED", "reason": "DRY_POWDER_FLOOR",
                    "required_reserve_cents": required_reserve}

        order_key = str(candidate.get("client_order_id") or uuid4())
        instrument = str(candidate.get("ticker", candidate.get("token_id", candidate.get("contract_id", ""))))
        payload = {"client_order_id": order_key, "side": "BUY", "quantity": quantity,
                   "limit_price_cents": limit_cents, "post_only": True, "fee_cents": 0}
        payload["ticker" if venue == "KALSHI" else "token_id"] = instrument
        response = await self.clients[venue].place_order(payload)
        order = {**payload, "venue": venue, "contract_id": instrument,
                 "notional_cents": notional_cents, "response": response,
                 "status": response.get("status", "resting")}
        self.routed_orders[response.get("order_id", order_key)] = order
        self.available_capital_cents -= notional_cents
        # PositionBook is also the local inventory registry; pending orders are
        # exposed separately so a route cannot be mistaken for an execution fill.
        if not hasattr(self.position_book, "routed_orders"):
            self.position_book.routed_orders = []
        self.position_book.routed_orders.append(order)
        return order

    async def route_order(self, candidate: Dict[str, Any], allocated_capital_cents: Optional[int] = None) -> Dict[str, Any]:
        return await self.dispatch(candidate, allocated_capital_cents)
