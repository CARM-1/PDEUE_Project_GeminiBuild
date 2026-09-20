from decimal import Decimal

import pytest

from app.domain.atomic_leg_coordinator import AtomicLegCoordinator
from app.domain.cross_venue_manager import CrossVenueManager
from app.domain.dynamic_spread_kelly import DynamicSpreadKellyEngine
from app.domain.founder_workspace import FounderWorkspaceService
from app.domain.priority_eviction import PriorityEvictionManager


def test_spread_fraction_at_one_cent_is_quarter_kelly():
    assert DynamicSpreadKellyEngine.spread_fraction("0.01") == Decimal("0.25")


def test_spread_fraction_scales_linearly():
    assert DynamicSpreadKellyEngine.spread_fraction("0.03") == Decimal("0.15")


def test_spread_fraction_has_defensive_floor():
    assert DynamicSpreadKellyEngine.spread_fraction("0.20") == Decimal("0.05")


def test_kelly_uses_waterfall_adjusted_net_odds():
    result = DynamicSpreadKellyEngine().calculate_allocation(
        model_probability=.70, market_probability=.50, spread=.01, total_equity_cents=10_000)
    assert result.b_net == pytest.approx(.87)


def test_kelly_is_capped_at_five_percent_of_equity():
    result = DynamicSpreadKellyEngine().calculate_allocation(
        model_probability=.99, market_probability=.10, spread=.01, total_equity_cents=10_001)
    assert result.allocation_cents == 500


def test_kelly_negative_edge_allocates_zero_integer_cents():
    result = DynamicSpreadKellyEngine().calculate_allocation(
        model_probability=.20, market_probability=.50, spread=.01, total_equity_cents=10_000)
    assert result.allocation_cents == 0
    assert type(result.allocation_cents) is int


def test_if008_snapshot_uses_spread_and_midpoint():
    snapshot = {"yes_bid": .40, "yes_ask": .42}
    result = DynamicSpreadKellyEngine().calculate_from_snapshot(
        snapshot, model_probability=.60, total_equity_cents=10_000)
    assert result.allocation_fraction == pytest.approx(.20)


def test_kelly_rejects_non_integer_money():
    with pytest.raises(ValueError, match="integer"):
        DynamicSpreadKellyEngine().calculate_allocation(
            model_probability=.7, market_probability=.5, spread=.01, total_equity_cents=100.5)


def _candidate(edge=.03):
    return {"net_edge": edge, "proposed_stake_cents": 10, "expiry_hours": 1}


def test_eviction_default_capacity_is_six():
    assert PriorityEvictionManager().max_concurrent_orders == 6


def test_candidate_below_three_percent_is_rejected():
    decision = PriorityEvictionManager().evaluate_preemption(_candidate(.0299), 10_000, 0)
    assert decision["reason"] == "EDGE_BELOW_ADMISSION_THRESHOLD"


def test_full_board_preempts_lowest_edge_at_ten_point_delta():
    manager = PriorityEvictionManager()
    for i in range(6):
        manager.register_resting_order(str(i), "T", "WEATHER", .04 + i / 100, 10)
    decision = manager.evaluate_preemption(_candidate(.14), 10_000, 60)
    assert decision["eviction_target"]["order_id"] == "0"


def test_partially_filled_order_cannot_be_evicted():
    manager = PriorityEvictionManager(max_concurrent_orders=1)
    manager.register_resting_order("p", "T", "SPORTS", .03, 10)
    manager.mark_order_partially_filled("p")
    decision = manager.evaluate_preemption(_candidate(.50), 10_000, 10)
    assert decision["reason"] == "NO_UNFILLED_RESTING_ORDERS_AVAILABLE"
    with pytest.raises(ValueError, match="cannot be evicted"):
        manager.execute_eviction("p")


def test_atomic_routes_lower_depth_leg_first():
    coordinator = AtomicLegCoordinator()
    result = coordinator.coordinate_legs(
        {"leg_id": "deep", "depth_cents": 1000}, {"leg_id": "thin", "depth_cents": 100})
    assert result["primary_fill"]["leg_id"] == "thin"
    assert result["primary_fill"]["order_type"] == "RESTING_LIMIT"


def test_atomic_uses_wider_spread_as_liquidity_tiebreaker():
    legs = AtomicLegCoordinator.route_order([
        {"leg_id": "narrow", "depth_cents": 100, "spread": .01},
        {"leg_id": "wide", "depth_cents": 100, "spread": .03},
    ])
    assert legs[0]["leg_id"] == "wide"


def test_atomic_leg_two_at_750ms_is_on_time():
    result = AtomicLegCoordinator().coordinate_legs({}, {}, simulate_leg2_latency_sec=.750)
    assert result["is_atomic_success"] is True


def test_atomic_timeout_fires_bounded_ioc_scratch():
    result = AtomicLegCoordinator().coordinate_legs(
        {"scratch_loss_cents": 50}, {}, simulate_leg2_latency_sec=.751, max_loss_budget_cents=20)
    assert result["scratch_event"]["order_type"] == "IOC_MARKETABLE_LIMIT"
    assert result["scratch_event"]["realized_loss_cents"] == 20


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def test_cross_venue_emits_rebalance_above_fifteen_percent():
    status = CrossVenueManager(5800, 4200).collateral_status()
    assert status["event"] == "REBALANCE_REQUIRED"


def test_cross_venue_does_not_emit_at_exact_boundary():
    status = CrossVenueManager(5750, 4250).collateral_status()
    assert status["event"] == "BALANCED"


def test_token_bucket_allows_ten_then_returns_jittered_backoff():
    clock = Clock()
    manager = CrossVenueManager(clock=clock, jitter=lambda low, high: high)
    assert all(manager.acquire("kalshi")["allowed"] for _ in range(10))
    throttled = manager.acquire("kalshi")
    assert throttled == {"allowed": False, "retry_after_seconds": .125}


def test_token_buckets_are_independent_per_venue():
    manager = CrossVenueManager(clock=Clock())
    for _ in range(10):
        manager.acquire("KALSHI")
    assert manager.acquire("POLYMARKET")["allowed"] is True


def test_dry_powder_policy_resolves_to_40_percent_with_40_dollar_floor():
    service = FounderWorkspaceService()
    service.ledger.balance_cents = 20_000
    service.authoritative_as_of_utc = "2026-09-20T00:00:00+00:00"
    data = service.capital_summary().data
    assert data.dry_powder_floor_cents == 8000
    assert data.dry_powder_policy_status == "QUALIFIED"
    assert data.dry_powder_policy_version == "rcb.v1"


def test_dry_powder_absolute_floor_is_4000_cents():
    service = FounderWorkspaceService()
    service.ledger.balance_cents = 1000
    service.authoritative_as_of_utc = "2026-09-20T00:00:00+00:00"
    assert service.capital_summary().data.dry_powder_floor_cents == 4000
