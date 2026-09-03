from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

class KalshiVenueAdapter:
    DEFAULT_FEE_RATE = 0.01

    def normalize_market_ladder(self, raw_markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ladder = []
        for m in raw_markets:
            ticker = m.get('ticker') or m.get('contract_id', '')
            strike = m.get('strike_val') or m.get('floor_strike') or m.get('strike_temp_c', 0.0)
            yes_bid = float(m.get('yes_bid_dollars', m.get('yes_bid', 0.0)))
            yes_ask = float(m.get('yes_ask_dollars', m.get('yes_ask', 1.0)))
            ladder.append({
                'contract_id': ticker,
                'strike_temp_c': float(strike),
                'yes_bid': round(yes_bid, 4),
                'yes_ask': round(yes_ask, 4),
                'venue': 'KALSHI'
            })
        return sorted(ladder, key=lambda x: x['strike_temp_c'])

    def normalize_order_book(self, market_id: str, contract_id: str, raw_book: Dict[str, Any]) -> Dict[str, Any]:
        yes_bids = raw_book.get('yes_bids', [])
        yes_asks = raw_book.get('yes_asks', [])
        best_bid = float(yes_bids[0]['price']) if yes_bids else float(raw_book.get('yes_bid', 0.0))
        best_ask = float(yes_asks[0]['price']) if yes_asks else float(raw_book.get('yes_ask', 1.0))
        return {
            'market_id': market_id,
            'contract_id': contract_id,
            'yes_bid': round(best_bid, 4),
            'yes_ask': round(best_ask, 4),
            'spread': round(max(0.0, best_ask - best_bid), 4),
            'timestamp': raw_book.get('timestamp', datetime.now(timezone.utc).isoformat())
        }

    def build_order_payload(self, order_intent: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'ticker': order_intent['contract_id'],
            'action': order_intent['side'].lower(),
            'type': 'limit',
            'yes_price': int(round(order_intent['price'] * 100)),
            'count': order_intent['quantity'],
            'client_order_id': order_intent['idempotency_key']
        }
