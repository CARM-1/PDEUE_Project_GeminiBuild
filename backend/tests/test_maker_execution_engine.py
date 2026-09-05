from app.domain.maker_execution_engine import MakerExecutionEngine

def test_maker_bid_happy_path():
    engine = MakerExecutionEngine(maker_fee_rate=0.0, taker_fee_rate=0.01)
    res = engine.construct_maker_bid(best_bid=0.40, best_ask=0.46, model_prob=0.55, min_margin=0.02)
    assert res['status'] == 'POSTED'
    assert res['maker_price'] == 0.41
    assert res['spread_discount'] == 0.05
    assert res['net_basis_advantage'] > 0.05

def test_maker_bid_abstained_when_margin_thin():
    engine = MakerExecutionEngine()
    res = engine.construct_maker_bid(best_bid=0.40, best_ask=0.45, model_prob=0.42, min_margin=0.02)
    assert res['status'] == 'ABSTAINED'
    assert res['reason'] == 'MAKER_MARGIN_INSUFFICIENT'

def test_maker_fill_probability_estimation():
    engine = MakerExecutionEngine()
    assert engine.evaluate_fill_probability(queue_ahead=0, cycle_volume=10) == 1.0
    assert engine.evaluate_fill_probability(queue_ahead=100, cycle_volume=0) == 0.0
    assert engine.evaluate_fill_probability(queue_ahead=50, cycle_volume=50) == 0.5
