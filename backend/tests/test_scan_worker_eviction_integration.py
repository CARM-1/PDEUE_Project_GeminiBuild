import pytest
from app.domain.scan_worker import AutonomousScanWorker
from app.domain.capital_ledger import CapitalLedger
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.accounting_gateway import AccountingGateway
from app.domain.position_book import PositionBook

def test_scan_worker_default_eviction_manager():
    """Validates AutonomousScanWorker initializes with default eviction manager."""
    worker = AutonomousScanWorker()
    assert isinstance(worker.eviction_manager, PriorityEvictionManager)
    assert worker.eviction_manager.max_concurrent_orders == 12
    assert worker.eviction_manager.dry_powder_floor_pct == 0.40

def test_scan_worker_preemption_wiring():
    """Validates AutonomousScanWorker integration with PriorityEvictionManager and Ledger."""
    ledger = CapitalLedger(initial_balance_cents=10000)
    eviction_mgr = PriorityEvictionManager()
    worker = AutonomousScanWorker(ledger=ledger, eviction_manager=eviction_mgr)
    
    assert worker.eviction_manager.max_concurrent_orders == 12
    assert worker.eviction_manager.dry_powder_floor_pct == 0.40

    # Populate all 12 resting order slots
    for i in range(1, 13):
        worker.eviction_manager.register_resting_order(
            order_id=f"RESTING-0{i}",
            ticker=f"TICKER-0{i}",
            domain="WEATHER",
            net_edge=0.04 + (i * 0.01),
            stake_cents=500
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
        currently_committed_cents=6000
    )
    
    assert decision["admitted"] is True
    assert decision["reason"] == "PREEMPTION_APPROVED"
    assert decision["eviction_target"]["order_id"] == "RESTING-01"

    # Execute eviction through worker
    evicted = worker.execute_eviction("RESTING-01")
    assert evicted["status"] == "CANCELLED_EVICTED"
    assert len(worker.eviction_manager.resting_orders) == 11
    assert worker.stats["total_evictions_executed"] == 1


def test_daemon_cycle_reports_n12_envelope_and_all_categories():
    worker = AutonomousScanWorker(ledger=CapitalLedger(initial_balance_cents=10_000))
    result = worker.run_single_cycle()

    assert result["slot_capacity"] == 12
    assert result["dry_powder_floor_cents"] == 4_000
    assert {order["category"] for order in result["dispatched_orders"]} == {
        "WEATHER", "CRYPTO", "MACRO", "SPORTS",
    }


def test_daemon_cycle_recycles_complete_sets_before_dispatch():
    ledger = CapitalLedger(initial_balance_cents=0)
    ledger.register_member_account("SCMA-1", 0)
    book = PositionBook()
    book.record_fill("C-1", "KALSHI", "WEATHER", "BUY_YES", 0.40, 8, 320, "SCMA-1")
    book.record_fill("C-1", "KALSHI", "WEATHER", "BUY_NO", 0.50, 5, 250, "SCMA-1")
    worker = AutonomousScanWorker(ledger=ledger, position_book=book)

    result = worker.run_single_cycle()

    assert result["merged_shares_count"] == 5
    assert ledger.members["SCMA-1"]["balance_cents"] == 500


def test_daemon_cycle_stages_signed_if038_for_float_surplus():
    ledger = CapitalLedger(initial_balance_cents=2_575_125)
    gateway = AccountingGateway(secret_key="scan-worker-test-key")
    worker = AutonomousScanWorker(ledger=ledger, accounting_gateway=gateway)

    result = worker.run_single_cycle()

    assert result["staged_sweeps_count"] == 1
    assert ledger.balance_cents == 2_500_000
    event = gateway.event_outbox[0]
    assert event["payload"]["amount_cents"] == 75_125
    canonical = gateway._canonicalize_payload(event["payload"])
    assert gateway.verify_signature(canonical, event["signature_hmac_sha256"])
