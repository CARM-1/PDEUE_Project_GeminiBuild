from app.domain.walk_forward_simulation import WalkForwardBenchmark

def test_walk_forward_benchmark_execution():
    sim = WalkForwardBenchmark(initial_capital_cents=10000)
    ticks = [
        {'contract_id': 'WX-01', 'entry_ask': 0.12, 'peak_midpoint': 0.85, 'final_payout': 1.0, 'fee_rate': 0.01},
        {'contract_id': 'MACRO-01', 'entry_ask': 0.50, 'peak_midpoint': 0.65, 'final_payout': 0.0, 'fee_rate': 0.01},
        {'contract_id': 'SPORTS-01', 'entry_ask': 0.40, 'peak_midpoint': 0.92, 'final_payout': 1.0, 'fee_rate': 0.01},
        {'contract_id': 'CRYPTO-01', 'entry_ask': 0.20, 'peak_midpoint': 0.25, 'final_payout': 0.0, 'fee_rate': 0.00}
    ]
    res = sim.run_simulation(ticks)
    assert res['status'] == 'COMPLETED'
    assert res['total_trades'] == 4
    assert res['early_harvested_count'] >= 1
    assert res['hybrid_c_final_cents'] > sim.initial_capital_cents
