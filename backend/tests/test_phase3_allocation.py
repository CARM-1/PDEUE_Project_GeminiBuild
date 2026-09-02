from app.domain.portfolio_allocation import PortfolioAllocationEngine

def test_kelly_allocation_and_max_bounds():
    engine = PortfolioAllocationEngine(kelly_fraction=0.25, max_position_pct=0.10)
    res = engine.calculate_kelly_stake(0.70, 0.50, 10000.0)
    assert res["recommended_stake"] == 1000.0
    assert res["stake_pct"] == 0.10
    
    no_edge = engine.calculate_kelly_stake(0.40, 0.50, 10000.0)
    assert no_edge["recommended_stake"] == 0.0
