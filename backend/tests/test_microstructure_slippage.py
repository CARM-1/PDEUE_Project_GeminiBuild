from app.domain.market_depth import MarketDepthEngine

def test_thin_order_book_slippage_exceeded():
    depth = MarketDepthEngine(max_slippage_pct=0.015)
    book = [
        {'price': 0.40, 'size': 10.0},
        {'price': 0.48, 'size': 50.0}
    ]
    res = depth.evaluate_order_depth(book, requested_volume=40.0)
    assert res['executable'] is False
    assert res['reason'] == 'SLIPPAGE_EXCEEDED'
    assert res['slippage_pct'] > 0.015

def test_insufficient_liquidity():
    depth = MarketDepthEngine()
    book = [{'price': 0.50, 'size': 20.0}]
    res = depth.evaluate_order_depth(book, requested_volume=50.0)
    assert res['executable'] is False
    assert res['reason'] == 'INSUFFICIENT_LIQUIDITY'

def test_net_edge_friction_hurdle():
    depth = MarketDepthEngine(fee_rate=0.01)
    res_blocked = depth.evaluate_net_edge_friction(raw_edge=0.04, spread=0.05)
    assert res_blocked['admissible'] is False
    assert res_blocked['reason'] == 'FRICTION_ELIMINATES_EDGE'

    res_pass = depth.evaluate_net_edge_friction(raw_edge=0.15, spread=0.02)
    assert res_pass['admissible'] is True
    assert res_pass['net_edge'] > 0.0
