from fastapi.testclient import TestClient

from app.domain.historical_corpus import get_historical_tick_corpus
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.walk_forward_simulation import WalkForwardBenchmark
from app.main import app


def benchmark():
    return WalkForwardBenchmark(starting_cents=10_000).run()


def test_walk_forward_48_contracts_reaches_positive_expectancy():
    result = benchmark()
    assert result["total_contracts"] == 48
    assert result["total_pnl_cents"] > 0


def test_strategy_d_maker_saves_fees_vs_taker_drag():
    result = benchmark()
    assert result["maker_fee_cents"] == 0
    assert result["fee_savings_cents"] > 0


def test_strict_pit_timestamp_ordering_no_lookahead_bias():
    corpus = get_historical_tick_corpus()
    assert all(tick["observed_at"] < tick["decision_at"] for tick in corpus)
    assert [tick["decision_at"] for tick in corpus] == sorted(tick["decision_at"] for tick in corpus)


def test_concurrency_n12_preserves_dry_powder_floor_under_saturation():
    result = benchmark()
    manager = PriorityEvictionManager(max_concurrent_orders=12)
    for index in range(12):
        manager.register_resting_order(f"order-{index}", edge=index / 100, amount_cents=100)
    rejected = manager.evaluate_preemption({"net_edge": .19, "proposed_stake_cents": 2_001}, 10_000, 4_000)
    assert result["priority_capacity"] == 12
    assert result["dry_powder_floor_cents"] == 4_000
    assert not rejected["admitted"]


def test_waterfall_exact_cent_conservation_across_replay():
    waterfall = benchmark()["waterfall"]
    assert waterfall["member_scma_cents"] + waterfall["cfcp_cents"] + waterfall["faep_cents"] == waterfall["realized_profit_cents"]


def test_simulation_benchmark_endpoint_returns_200_and_expected_keys():
    response = TestClient(app).get("/api/v1/operator/simulation/benchmark")
    assert response.status_code == 200
    assert {"total_pnl_cents", "roi_pct", "fee_savings_cents", "equity_curve_points"} <= response.json().keys()


def test_legacy_portal_hub_preserved():
    html = TestClient(app).get("/dashboard").text
    assert '<div style="display:none" id="legacyPortalHub">' in html
