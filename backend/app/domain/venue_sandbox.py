from typing import Dict, Any, List
import uuid
from datetime import datetime, timezone

class KalshiSandboxAdapter:
    def __init__(self, api_key: str = "sandbox_key"):
        self.api_key = api_key
        self.orders: Dict[str, Dict[str, Any]] = {}

    def get_market_book(self, ticker: str) -> Dict[str, Any]:
        return {
            "ticker": ticker,
            "yes_bid": 0.42,
            "yes_ask": 0.45,
            "volume": 12500,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def place_order(self, ticker: str, action: str, count: int, price_cents: int) -> Dict[str, Any]:
        order_id = f"KALSHI-SB-{uuid.uuid4().hex[:8]}"
        order = {
            "order_id": order_id,
            "ticker": ticker,
            "action": action,
            "count": count,
            "price_cents": price_cents,
            "status": "FILLED",
            "venue": "KALSHI_SANDBOX"
        }
        self.orders[order_id] = order
        return order
