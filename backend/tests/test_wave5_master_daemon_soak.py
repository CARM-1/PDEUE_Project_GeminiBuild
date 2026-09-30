"""Wave 5 master daemon acceptance and qualification soak tests."""
from fastapi.testclient import TestClient

from app.domain.accounting_gateway import AccountingGateway
from app.domain.capital_ledger import CapitalLedger
from app.domain.daemon_loop import AutonomousExecutionLoop
from app.domain.settlement_reconciler import SettlementReconciler
from app.main import app
from scripts.run_master_qualification_soak import run_qualification_soak


def test_daemon_loop_executes_autonomous_maker_cycle():
    loop = AutonomousExecutionLoop()
    result = loop.run_cycle()
    assert result["dispatched_count"] == 4
    assert {order["category"] for order in result["dispatched_orders"]} == {
        "WEATHER", "MACRO", "SPORTS", "CRYPTO"}
    assert all(order["post_only"] and order["fee_cents"] == 0 for order in result["dispatched_orders"])
    assert all(order["limit_price_cents"] == order["notional_cents"] for order in result["dispatched_orders"])


def test_daemon_loop_preserves_dry_powder_floor_under_heavy_inflow():
    loop = AutonomousExecutionLoop(ledger=CapitalLedger(initial_balance_cents=10_000))
    feed = [{**loop.canonical_feed()[0], "ticker": f"LOAD-{i}",
             "contract_id": f"LOAD-{i}", "quantity": 20} for i in range(30)]
    result = loop.run_cycle(feed)
    assert result["cash_balance_cents"] >= result["dry_powder_floor_cents"]
    assert result["active_slots"] <= 12


def test_daemon_loop_evicts_lowest_edge_order_when_n12_saturated():
    loop = AutonomousExecutionLoop(ledger=CapitalLedger(initial_balance_cents=100_000))
    base = loop.canonical_feed()[0]
    for i in range(12):
        loop.dispatch_candidate({**base, "ticker": f"LOW-{i}", "contract_id": f"LOW-{i}",
                                 "net_edge": 0.01 + i / 1000})
    result = loop.dispatch_candidate({**base, "ticker": "HIGH", "contract_id": "HIGH",
                                      "net_edge": 0.30})
    assert result["contract_id"] == "HIGH"
    assert loop.evictions_executed == 1
    assert all(order["contract_id"] != "LOW-0" for order in loop.pending_orders.values())


def test_settlement_reconciler_distributes_87_10_3_waterfall():
    split = SettlementReconciler().calculate_waterfall_split(101)
    assert split == {"scma_cents": 87, "cfcp_cents": 10, "faep_cents": 4}
    assert sum(split.values()) == 101


def test_high_watermark_sweep_triggers_outbox_event_at_25000_threshold():
    gateway = AccountingGateway(secret_key="wave5")
    assert gateway.emit_capital_sweep(2_500_000) is None
    event = gateway.emit_capital_sweep(2_500_001)
    assert event["payload"]["amount_cents"] == 1
    assert event["event_type"] == "CAPITAL_SWEEP"
    assert gateway.verify_event(event)


def test_master_qualification_soak_completes_50_cycles_cleanly():
    telemetry = run_qualification_soak()
    assert telemetry["cycles_completed"] == 50
    assert telemetry["orders_posted"] == 200
    assert telemetry["orders_filled"] == 196
    assert telemetry["final_equity_cents"] >= 10_000


def test_daemon_summary_endpoint_returns_valid_telemetry():
    response = TestClient(app).get("/api/v1/portal/telemetry/daemon-summary")
    assert response.status_code == 200
    body = response.json()
    assert body["slot_capacity"] == 12
    assert isinstance(body["active_maker_bids"], int)
    assert isinstance(body["total_capital_sweeps_emitted"], int)


def test_legacy_portal_hub_preserved():
    source = TestClient(app).get("/dashboard").text
    assert '<div style="display:none" id="legacyPortalHub">' in source
