from app.domain.pit_replay import PITReplayEngine

def test_pit_replay_snapshot_and_backtest():
    engine = PITReplayEngine()
    obs_data = [
        {"timestamp": "2026-09-02T12:00:00Z", "temp_c": 22.0},
        {"timestamp": "2026-09-02T15:00:00Z", "temp_c": 25.5},
        {"timestamp": "2026-09-02T19:00:00Z", "temp_c": 28.0}
    ]
    snapshot = engine.reconstruct_pit_snapshot("EVT_KORD_01", "2026-09-02T16:00:00Z", obs_data)
    assert snapshot["observation_count"] == 2
    assert snapshot["active_observation"]["temp_c"] == 25.5

    ticks = [
        {"raw_prob": 0.80, "yes_ask": 0.50, "outcome": 1},
        {"raw_prob": 0.30, "yes_ask": 0.35, "outcome": 0}
    ]
    results = engine.run_backtest_simulation(ticks, reliability_factor=0.95)
    assert results["total_trades"] == 1
    assert results["cumulative_edge"] > 0
