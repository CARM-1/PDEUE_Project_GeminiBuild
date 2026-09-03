from app.domain.market_depth import MarketDepthEngine

def test_market_depth_execution_and_slippage():
    engine = MarketDepthEngine(fee_rate=0.01)
    book = [
        {"price": 0.50, "size": 100.0},
        {"price": 0.52, "size": 200.0},
        {"price": 0.55, "size": 500.0}
    ]
    res = engine.evaluate_order_depth(book, 150.0)
    assert res["executable"] is True
    assert res["vwap"] == 0.5067
    assert res["slippage"] == 0.0067
    assert res["executed_volume"] == 150.0

def test_market_depth_insufficient_liquidity():
    engine = MarketDepthEngine()
    book = [{"price": 0.50, "size": 50.0}]
    res = engine.evaluate_order_depth(book, 100.0)
    assert res["executable"] is False
    assert res["reason"] == "INSUFFICIENT_LIQUIDITY"

def test_market_depth_empty_book():
    engine = MarketDepthEngine()
    res = engine.evaluate_order_depth([], 50.0)
    assert res["executable"] is False
    assert res["reason"] == "EMPTY_BOOK_OR_ZERO_VOLUME"
