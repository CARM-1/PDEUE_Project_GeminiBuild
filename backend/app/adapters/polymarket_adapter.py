from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

class PolymarketVenueAdapter:
    DEFAULT_FEE_RATE = 0.00

    def normalize_market_ladder(self, raw_tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ladder = []
        for t in raw_tokens:
            token_id = t.get('token_id') or t.get('asset_id', '')
            strike = t.get('strike_value', 0.0)
            yes_bid = float(t.get('price_bid', t.get('bid', 0.0)))
            yes_ask = float(t.get('price_ask', t.get('ask', 1.0)))
            ladder.append({
                'contract_id': token_id,
                'strike_temp_c': float(strike),
                'yes_bid': round(yes_bid, 4),
                'yes_ask': round(yes_ask, 4),
                'venue': 'POLYMARKET'
            })
        return sorted(ladder, key=lambda x: x['strike_temp_c'])

    def normalize_order_book(self, market_id: str, contract_id: str, raw_book: Dict[str, Any]) -> Dict[str, Any]:
        bids = raw_book.get('bids', [])
        asks = raw_book.get('asks', [])
        best_bid = float(bids[0]['price']) if bids else float(raw_book.get('yes_bid', 0.0))
        best_ask = float(asks[0]['price']) if asks else float(raw_book.get('yes_ask', 1.0))
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
            'token_id': order_intent['contract_id'],
            'side': order_intent['side'].upper(),
            'price': round(order_intent['price'], 4),
            'size': float(order_intent['quantity']),
            'client_order_id': order_intent['idempotency_key']
        }
