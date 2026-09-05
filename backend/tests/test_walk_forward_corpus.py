from app.domain.historical_corpus import get_historical_tick_corpus
from app.domain.walk_forward_simulation import WalkForwardBenchmark
from fastapi.testclient import TestClient
from app.main import app

def test_historical_corpus_composition():
    ticks = get_historical_tick_corpus()
    assert len(ticks) == 48
    cats = {t['category'] for t in ticks}
    assert cats == {'WEATHER', 'MACROECONOMIC', 'SPORTS', 'CRYPTO'}

def test_walk_forward_corpus_metrics():
    sim = WalkForwardBenchmark(initial_capital_cents=10000)
    res = sim.run_simulation(get_historical_tick_corpus())
    assert res['status'] == 'COMPLETED'
    assert res['total_trades'] == 48
    assert res['early_harvested_count'] > 5
    assert res['win_rate_pct'] > 40.0
    assert res['max_drawdown_pct'] >= 0.0
    assert res['total_friction_cents'] > 0
    assert res['hybrid_c_final_cents'] > 10000

def test_operator_analytics_corpus_endpoint():
    client = TestClient(app)
    res = client.get('/api/v1/operator/analytics/walk-forward-simulation')
    assert res.status_code == 200
    d = res.json()
    assert d['total_trades'] == 48
    assert 'sharpe_ratio' in d
    assert 'win_rate_pct' in d
    assert 'max_drawdown_pct' in d
