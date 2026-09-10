import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.domain.walk_forward_simulation import WalkForwardBenchmark
from app.domain.historical_corpus import get_historical_tick_corpus

def test_walk_forward_simulation_includes_strategy_d():
    corpus = get_historical_tick_corpus()
    benchmark = WalkForwardBenchmark(initial_capital_cents=10000)
    res = benchmark.run_simulation(corpus)

    assert res["status"] == "COMPLETED"
    assert res["total_trades"] == 48

    # Baseline C verification
    assert res["hybrid_c_final_cents"] == 28573
    assert res["hybrid_c_roi_pct"] == 185.73

    # Strategy D verification (+248.60% ROI, zero fee drag)
    assert res["strategy_d_final_cents"] == 34860
    assert res["strategy_d_roi_pct"] == 248.6
    assert res["strategy_d_win_rate_pct"] == 100.0
    assert res["strategy_d_max_drawdown_pct"] == 0.0
    assert res["strategy_d_total_friction_cents"] == 0
    assert res["strategy_d_held_maturity_count"] == 48

def test_operator_analytics_endpoint_serves_strategy_d():
    client = TestClient(app)
    res = client.get("/api/v1/operator/analytics/walk-forward-simulation")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "COMPLETED"
    assert "strategy_d_final_cents" in data
    assert data["strategy_d_final_cents"] == 34860
    assert data["strategy_d_roi_pct"] == 248.6
    assert data["strategy_d_total_friction_cents"] == 0
