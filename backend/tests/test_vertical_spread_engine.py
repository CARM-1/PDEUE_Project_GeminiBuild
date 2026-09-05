from app.domain.vertical_spread_engine import VerticalSpreadEngine

def test_monotonicity_inversion_detected():
    engine = VerticalSpreadEngine(fee_rate=0.01, min_profit_cents=2)
    ladder = [
        {'contract_id': 'KX-TEMP-70', 'strike_value': 70.0, 'yes_bid': 0.40, 'yes_ask': 0.45},
        {'contract_id': 'KX-TEMP-72', 'strike_value': 72.0, 'yes_bid': 0.52, 'yes_ask': 0.56}
    ]
    inversions = engine.detect_monotonicity_inversions(ladder)
    assert len(inversions) == 1
    inv = inversions[0]
    assert inv['type'] == 'MONOTONICITY_INVERSION'
    assert inv['buy_contract_id'] == 'KX-TEMP-70'
    assert inv['sell_contract_id'] == 'KX-TEMP-72'
    assert inv['net_profit_cents'] >= 2

def test_vertical_box_spread_arbitrage():
    engine = VerticalSpreadEngine(fee_rate=0.01, min_profit_cents=2)
    ladder = [
        {'contract_id': 'KX-TEMP-70', 'strike_value': 70.0, 'yes_ask': 0.38, 'no_ask': 0.64},
        {'contract_id': 'KX-TEMP-74', 'strike_value': 74.0, 'yes_ask': 0.15, 'no_ask': 0.55}
    ]
    boxes = engine.detect_vertical_box_spreads(ladder)
    assert len(boxes) == 1
    box = boxes[0]
    assert box['type'] == 'VERTICAL_BOX_ARBITRAGE'
    assert box['floor_profit_cents'] >= 2
    assert box['max_potential_profit_cents'] > 100

def test_efficient_ladder_produces_zero_arbitrage():
    engine = VerticalSpreadEngine()
    ladder = [
        {'contract_id': 'KX-TEMP-70', 'strike_value': 70.0, 'yes_bid': 0.60, 'yes_ask': 0.65, 'no_ask': 0.40},
        {'contract_id': 'KX-TEMP-72', 'strike_value': 72.0, 'yes_bid': 0.40, 'yes_ask': 0.45, 'no_ask': 0.60}
    ]
    res = engine.evaluate_ladder(ladder)
    assert res['inversions_count'] == 0
    assert res['box_spreads_count'] == 0
    assert len(res['opportunities']) == 0
