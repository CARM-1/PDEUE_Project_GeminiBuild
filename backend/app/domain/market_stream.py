from typing import Dict, Any, Optional
from datetime import datetime, timezone

class MarketStreamAdapter:
    def __init__(self, venue_id: str = "KALSHI"):
        self.venue_id = venue_id
        self.cache: Dict[str, Dict[str, Any]] = {}

    def update_order_book(self, ticker: str, yes_bid: float, yes_ask: float, volume: int = 0) -> Dict[str, Any]:
        spread = round(yes_ask - yes_bid, 4)
        mid_price = round((yes_bid + yes_ask) / 2.0, 4)
        book_data = {
            "venue": self.venue_id,
            "ticker": ticker,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "spread": spread,
            "mid_price": mid_price,
            "volume": volume,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        self.cache[ticker] = book_data
        return book_data

    def get_latest_book(self, ticker: str) -> Optional[Dict[str, Any]]:
        return self.cache.get(ticker)
