"""WP-5A adjudicated engine and autonomous-daemon regression vectors."""

from fastapi.testclient import TestClient

from app.domain.capital_ledger import CapitalLedger
from app.domain.lineage_hierarchy import get_lineage_service
from app.domain.position_book import PositionBook
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.scan_worker import AutonomousScanWorker
from app.domain.settlement_engine import SettlementEngine
from app.main import app


client = TestClient(app)


def test_waterfall_floors_every_share_and_assigns_all_residual_to_cfcp():
    engine = SettlementEngine()
    for gross_profit_cents in range(1, 10_001):
        split = engine.calculate_waterfall_split(gross_profit_cents)
        assert split["scma_cents"] == gross_profit_cents * 87 // 100
        assert split["faep_cents"] == gross_profit_cents * 3 // 100
        expected_cfcp = gross_profit_cents - split["scma_cents"] - split["faep_cents"]
        assert split["cfcp_cents"] == expected_cfcp
        assert sum(split.values()) == gross_profit_cents


def test_frozen_member_is_zero_bps_and_custodial_self_service_is_forbidden():
    service = get_lineage_service()
    service.restore_house(2)
    try:
        service.freeze_house(2)
        state = client.get(
            "/api/v1/portal/member/state",
            params={"scma_id": "SCMA-JULIAN_-A1F98B21"},
        )
        assert state.status_code == 200
        assert state.json()["is_frozen"] is True
        assert state.json()["risk_dial_pct"] == 0.0

        mutation = client.post(
            "/api/v1/portal/member/risk-dial",
            json={"scma_id": "SCMA-JULIAN_-A1F98B21", "requested_risk_pct": 0.5},
        )
        assert mutation.status_code == 403
        assert mutation.json()["detail"] == (
            "Custodial accounts require F2-H Head of Household authorization"
        )
    finally:
        service.restore_house(2)


def test_preemption_evicts_only_lowest_resting_bid_and_preserves_inventory():
    manager = PriorityEvictionManager(max_concurrent_orders=12)
    for index in range(12):
        order_id = f"ORDER-{index:02d}"
        manager.register_resting_order(
            order_id=order_id, net_edge=0.04 + index / 1000, stake_cents=500
        )
    manager.mark_order_filled("ORDER-11")

    decision = manager.evaluate_preemption(
        {"net_edge": 0.20, "proposed_stake_cents": 500, "expiry_hours": 1},
        total_equity_cents=10_000,
        currently_committed_cents=6_000,
    )
    assert decision["admitted"] is True
    assert decision["eviction_target"]["order_id"] == "ORDER-00"
    manager.execute_eviction("ORDER-00")
    assert "ORDER-11" in manager.filled_orders
    assert manager.filled_orders["ORDER-11"]["status"] == "FILLED"


def test_scan_cycle_burns_complete_set_and_releases_collateral_immediately():
    ledger = CapitalLedger(initial_balance_cents=0)
    ledger.register_member_account("SCMA-1", seed_capital_cents=0)
    book = PositionBook()
    book.record_fill("BINARY-1", "PAPER", "TEST", "BUY_YES", 0.4, 3, 120, "SCMA-1")
    book.record_fill("BINARY-1", "PAPER", "TEST", "BUY_NO", 0.5, 2, 100, "SCMA-1")
    worker = AutonomousScanWorker(ledger=ledger, position_book=book)

    assert worker._recycle_complete_sets() == 2
    assert ledger.members["SCMA-1"]["balance_cents"] == 200
    remaining = list(book.positions.values())
    assert len(remaining) == 1
    assert remaining[0]["outcome_side"] == "YES"
    assert remaining[0]["quantity"] == 1
