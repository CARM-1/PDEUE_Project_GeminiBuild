from app.adapters.kalshi_adapter import KalshiVenueAdapter
from app.adapters.polymarket_adapter import PolymarketVenueAdapter

def test_kalshi_adapter_ladder_normalization():
    adapter = KalshiVenueAdapter()
    raw = [
        {'ticker': 'KX-ORD-28', 'strike_val': 28.0, 'yes_bid': 0.05, 'yes_ask': 0.09},
        {'ticker': 'KX-ORD-24', 'strike_val': 24.0, 'yes_bid': 0.85, 'yes_ask': 0.89}
    ]
    ladder = adapter.normalize_market_ladder(raw)
    assert len(ladder) == 2
    assert ladder[0]['contract_id'] == 'KX-ORD-24'
    assert ladder[0]['strike_temp_c'] == 24.0
    assert ladder[1]['contract_id'] == 'KX-ORD-28'

def test_kalshi_order_payload_formatting():
    adapter = KalshiVenueAdapter()
    intent = {
        'contract_id': 'KX-ORD-24',
        'side': 'BUY',
        'price': 0.85,
        'quantity': 50,
        'idempotency_key': 'IDEM-K-100'
    }
    payload = adapter.build_order_payload(intent)
    assert payload['ticker'] == 'KX-ORD-24'
    assert payload['action'] == 'buy'
    assert payload['yes_price'] == 85
    assert payload['count'] == 50
    assert payload['client_order_id'] == 'IDEM-K-100'

def test_polymarket_adapter_ladder_and_order():
    adapter = PolymarketVenueAdapter()
    raw_tokens = [
        {'token_id': 'POLY-STRIKE-70', 'strike_value': 21.1, 'price_bid': 0.40, 'price_ask': 0.44}
    ]
    ladder = adapter.normalize_market_ladder(raw_tokens)
    assert len(ladder) == 1
    assert ladder[0]['venue'] == 'POLYMARKET'

    intent = {
        'contract_id': 'POLY-STRIKE-70',
        'side': 'BUY',
        'price': 0.44,
        'quantity': 100,
        'idempotency_key': 'IDEM-P-200'
    }
    order = adapter.build_order_payload(intent)
    assert order['token_id'] == 'POLY-STRIKE-70'
    assert order['side'] == 'BUY'
    assert order['price'] == 0.44
    assert order['size'] == 100.0
