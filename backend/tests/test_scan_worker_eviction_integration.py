import pytest
from app.domain.scan_worker import AutonomousScanWorker
from app.domain.capital_ledger import CapitalLedger
from app.domain.priority_eviction import PriorityEvictionManager

def test_scan_worker_default_eviction_manager():
    """Validates AutonomousScanWorker initializes with default eviction manager."""
    worker = AutonomousScanWorker()
    assert isinstance(worker.eviction_manager, PriorityEvictionManager)
    assert worker.eviction_manager.max_concurrent_orders == 5
    assert worker.eviction_manager.dry_powder_floor_pct == 0.40

def test_scan_worker_preemption_wiring():
    """Validates AutonomousScanWorker integration with PriorityEvictionManager and Ledger."""
    ledger = CapitalLedger(initial_balance_cents=10000)
    eviction_mgr = PriorityEvictionManager()
    worker = AutonomousScanWorker(ledger=ledger, eviction_manager=eviction_mgr)
    
    assert worker.eviction_manager.max_concurrent_orders == 5
    assert worker.eviction_manager.dry_powder_floor_pct == 0.40

    # Populate 5 resting orders
    for i in range(1, 6):
        worker.eviction_manager.register_resting_order(
            order_id=f"RESTING-0{i}",
            ticker=f"TICKER-0{i}",
            domain="WEATHER",
            net_edge=0.04 + (i * 0.01),
            stake_cents=1000
        )

    # Candidate with +25% edge evaluates for preemption
    candidate = {
        "ticker": "HIGH-ALPHA-01",
        "net_edge": 0.25,
        "proposed_stake_cents": 500,
        "expiry_hours": 2.0
    }
    
    decision = worker.evaluate_candidate_preemption(
        candidate=candidate,
        total_equity_cents=10000,
        currently_committed_cents=5000
    )
    
    assert decision["admitted"] is True
    assert decision["reason"] == "PREEMPTION_APPROVED"
    assert decision["eviction_target"]["order_id"] == "RESTING-01"

    # Execute eviction through worker
    evicted = worker.execute_eviction("RESTING-01")
    assert evicted["status"] == "CANCELLED_EVICTED"
    assert len(worker.eviction_manager.resting_orders) == 4
    assert worker.stats["total_evictions_executed"] == 1
