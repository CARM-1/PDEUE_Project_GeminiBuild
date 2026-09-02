from app.domain.market_comparator import MarketComparator

def test_market_comparator_edge_calculation():
    comparator = MarketComparator()
    snapshot = {"market_id": "MKT-W01", "contract_id": "CT-W01", "yes_bid": 0.40, "yes_ask": 0.44, "timestamp": "2026-09-01T12:00:00Z"}
    metrics = comparator.calculate_edge(model_prob=0.60, market_snapshot=snapshot)
    assert metrics["implied_probability"] == 0.42
    assert metrics["raw_edge"] == 0.18
    assert metrics["buy_yes_advantage"] == 0.16
