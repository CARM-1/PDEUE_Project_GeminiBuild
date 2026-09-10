import pytest
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.capital_ledger import CapitalLedger
from app.domain.two_tier_risk import TwoTierRiskEnvelope

def test_eviction_manager_initialization_defaults():
    mgr = PriorityEvictionManager()
    assert mgr.max_concurrent_orders == 5
    assert mgr.dry_powder_floor_pct == 0.40
    assert mgr.max_expiry_hours == 6.0
    assert mgr.preemption_alpha_threshold == 0.20
    assert mgr.min_edge_delta == 0.10

def test_expiry_horizon_hard_filter_rejection():
    mgr = PriorityEvictionManager()
    candidate = {"ticker": "KX-LONG-01", "net_edge": 0.25, "proposed_stake_cents": 300, "expiry_hours": 12.0}
    res = mgr.evaluate_preemption(candidate, total_equity_cents=10000, currently_committed_cents=0)
    assert res["admitted"] is False
    assert res["reason"] == "EXPIRY_EXCEEDS_HORIZON_CEILING"

def test_normal_admission_within_capacity_and_dry_powder():
    mgr = PriorityEvictionManager()
    candidate = {"ticker": "KX-SHORT-01", "net_edge": 0.12, "proposed_stake_cents": 300, "expiry_hours": 3.0}
    # 60% of 10,000 = 6,000 max active. 1,000 committed leaves 5,000 available.
    res = mgr.evaluate_preemption(candidate, total_equity_cents=10000, currently_committed_cents=1000)
    assert res["admitted"] is True
    assert res["reason"] == "NORMAL_ADMISSION"
    assert res["eviction_target"] is None

def test_preemption_approved_when_resting_bid_outperformed():
    mgr = PriorityEvictionManager()
    # Fill all 5 concurrent slots with low/moderate edge resting orders
    for i in range(1, 6):
        mgr.register_resting_order(f"ORD-0{i}", f"TICKER-0{i}", "WEATHER", net_edge=0.05 + (i * 0.01), stake_cents=1000)

    # Candidate with +24% edge arrives, 2 hours expiry
    candidate = {"ticker": "KX-HIGH-ALPHA", "net_edge": 0.24, "proposed_stake_cents": 500, "expiry_hours": 2.0}
    res = mgr.evaluate_preemption(candidate, total_equity_cents=10000, currently_committed_cents=5000)

    assert res["admitted"] is True
    assert res["reason"] == "PREEMPTION_APPROVED"
    assert res["eviction_target"]["order_id"] == "ORD-01"  # Lowest edge (6%)
    assert res["edge_delta"] == pytest.approx(0.18, 0.001)

    # Execute eviction
    evicted = mgr.execute_eviction("ORD-01")
    assert evicted["status"] == "CANCELLED_EVICTED"
    assert "ORD-01" not in mgr.resting_orders
    assert len(mgr.eviction_history) == 1

def test_preemption_rejected_when_candidate_alpha_below_threshold():
    mgr = PriorityEvictionManager()
    for i in range(1, 6):
        mgr.register_resting_order(f"ORD-0{i}", f"TICKER-0{i}", "SPORTS", net_edge=0.04, stake_cents=1000)

    # Candidate has +14% edge (below the 20% preemption requirement)
    candidate = {"ticker": "POLY-MODERATE", "net_edge": 0.14, "proposed_stake_cents": 400, "expiry_hours": 1.5}
    res = mgr.evaluate_preemption(candidate, total_equity_cents=10000, currently_committed_cents=5000)

    assert res["admitted"] is False
    assert res["reason"] == "ALPHA_BELOW_PREEMPTION_THRESHOLD"
    assert res["eviction_target"] is None

def test_preemption_rejected_when_edge_delta_insufficient():
    mgr = PriorityEvictionManager()
    for i in range(1, 6):
        mgr.register_resting_order(f"ORD-0{i}", f"TICKER-0{i}", "MACRO", net_edge=0.16, stake_cents=1000)

    # Candidate has +21% edge (meets 20% threshold, but delta vs 16% is only 5% < 10% min delta)
    candidate = {"ticker": "KX-CLOSE-ALPHA", "net_edge": 0.21, "proposed_stake_cents": 400, "expiry_hours": 4.0}
    res = mgr.evaluate_preemption(candidate, total_equity_cents=10000, currently_committed_cents=5000)

    assert res["admitted"] is False
    assert "INSUFFICIENT_DELTA" in res["reason"]

def test_filled_inventory_is_strictly_immune_from_eviction():
    mgr = PriorityEvictionManager()
    # 5 orders all filled
    for i in range(1, 6):
        oid = f"ORD-FILL-0{i}"
        mgr.register_resting_order(oid, f"TICKER-0{i}", "CRYPTO", net_edge=0.03, stake_cents=1000)
        mgr.mark_order_filled(oid)

    candidate = {"ticker": "KX-MASSIVE-ALPHA", "net_edge": 0.35, "proposed_stake_cents": 500, "expiry_hours": 1.0}
    res = mgr.evaluate_preemption(candidate, total_equity_cents=10000, currently_committed_cents=5000)

    # Cannot evict filled orders (prevents taker spread crossing)
    assert res["admitted"] is False
    assert res["reason"] == "NO_UNFILLED_RESTING_ORDERS_AVAILABLE"

    with pytest.raises(ValueError, match="cannot be evicted"):
        mgr.execute_eviction("ORD-FILL-01")
