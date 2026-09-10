from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_walk_forward_analytics_endpoint():
    res = client.get('/api/v1/operator/analytics/walk-forward-simulation')
    assert res.status_code == 200
    data = res.json()
    assert data['status'] == 'COMPLETED'
    assert data['total_trades'] >= 48
    assert 'hybrid_c_roi_pct' in data
    assert 'sharpe_ratio' in data
    assert 'win_rate_pct' in data
    assert 'max_drawdown_pct' in data
    assert data['early_harvested_count'] >= 1
    assert data['hybrid_c_final_cents'] >= 10000

    # Strategy D verification in analytics response
    assert data['strategy_d_final_cents'] == 34860
    assert data['strategy_d_roi_pct'] == 248.60
    assert data['strategy_d_win_rate_pct'] == 100.0
    assert data['strategy_d_max_drawdown_pct'] == 0.0
    assert data['strategy_d_total_friction_cents'] == 0

def test_dashboard_cockpit_renders_strategy_d_benchmark():
    res = client.get('/dashboard')
    assert res.status_code == 200
    html = res.text

    assert "Empirical Walk-Forward Simulation" in html
    assert "Strategy D (Inside Maker Core)" in html
    assert "wf-strat-d-equity" in html
    assert "wf-strat-d-roi" in html
    assert "wf-base-a-equity" in html
    assert "wf-base-c-equity" in html
    assert "/api/v1/operator/analytics/walk-forward-simulation" in html
