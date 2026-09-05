from fastapi.testclient import TestClient
from app.main import app

def test_walk_forward_analytics_endpoint():
    client = TestClient(app)
    res = client.get('/api/v1/operator/analytics/walk-forward-simulation')
    assert res.status_code == 200
    data = res.json()
    assert data['status'] == 'COMPLETED'
    assert data['total_trades'] == 4
    assert 'hybrid_c_roi_pct' in data
    assert data['early_harvested_count'] >= 1
    assert data['hybrid_c_final_cents'] >= 10000
