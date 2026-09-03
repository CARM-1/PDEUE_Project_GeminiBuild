from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import json

class PolymarketVenueAdapter:
    DEFAULT_FEE_RATE = 0.00

    def normalize_market_ladder(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ladder = []
        for item in raw_data:
            if 'markets' in item and isinstance(item['markets'], list):
                for m in item['markets']:
                    tid = m.get('id') or m.get('conditionId', 'POLY-LIVE')
                    prices_raw = m.get('outcomePrices', '["0.50", "0.50"]')
                    try:
                        prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                        p_yes = float(prices[0])
                    except Exception:
                        p_yes = 0.50
                    yes_bid = max(0.01, round(p_yes - 0.02, 4))
                    yes_ask = min(0.99, round(p_yes + 0.02, 4))
                    ladder.append({
                        'contract_id': f'POLY-{tid[:12]}',
                        'strike_temp_c': 120000.0,
                        'yes_bid': yes_bid,
                        'yes_ask': yes_ask,
                        'venue': 'POLYMARKET'
                    })
            else:
                token_id = item.get('token_id') or item.get('asset_id', 'POLY-CRYPTO')
                strike = float(item.get('strike_value', item.get('strike_temp_c', 120000.0)))
                yes_bid = float(item.get('price_bid', item.get('yes_bid', 0.20)))
                yes_ask = float(item.get('price_ask', item.get('yes_ask', 0.24)))
                ladder.append({
                    'contract_id': token_id,
                    'strike_temp_c': strike,
                    'yes_bid': round(yes_bid, 4),
                    'yes_ask': round(yes_ask, 4),
                    'venue': 'POLYMARKET'
                })
        return sorted(ladder, key=lambda x: x['strike_temp_c'])

    def build_order_payload(self, order_intent: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'token_id': order_intent['contract_id'],
            'side': order_intent['side'].upper(),
            'price': round(order_intent['price'], 4),
            'size': float(order_intent['quantity']),
            'client_order_id': order_intent['idempotency_key']
        }
