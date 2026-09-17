import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.domain.settlement_engine import SettlementEngine

client = TestClient(app)

def test_binary_yes_settlement_87_10_3_exact_cent_conservation():
    engine = SettlementEngine()
    # 3,958 contracts @ 3¢ ($118.75 cost)
    # YES payout = $3,958.00 (395,800 cents)
    # Net profit = 395,800 - 11,875 = 383,925 cents ($3,839.25)
    rec = engine.resolve_contract("KX-MIA-FRZ-32", "YES", 3958, 11875)
    assert rec["gross_payout_cents"] == 395800
    assert rec["net_pnl_cents"] == 383925

    w = rec["waterfall"]
    # 87% of 383,925 = 334,014 cents ($3,340.14)
    assert w["scma_reinvest_cents"] == 334014
    # 10% of 383,925 = 38,392 cents ($383.92)
    assert w["cfcp_shield_cents"] == 38392
    # 3% remainder = 383,925 - 334,014 - 38,392 = 11,519 cents ($115.19)
    assert w["faep_endowment_cents"] == 11519
    # Zero-remainder proof
    assert w["scma_reinvest_cents"] + w["cfcp_shield_cents"] + w["faep_endowment_cents"] == rec["net_pnl_cents"]

def test_binary_no_settlement_loss_isolation():
    engine = SettlementEngine()
    rec = engine.resolve_contract("KX-MIA-FRZ-32", "NO", 3958, 11875)
    assert rec["gross_payout_cents"] == 0
    assert rec["net_pnl_cents"] == -11875
    # Invariant: Losses never touch CFCP or FAEP
    assert rec["waterfall"]["cfcp_shield_cents"] == 0
    assert rec["waterfall"]["faep_endowment_cents"] == 0
    assert rec["waterfall"]["scma_reinvest_cents"] == -11875

def test_settlement_api_workflow():
    res = client.post(
        "/api/v1/operator/settlement/resolve",
        json={"contract_ticker": "KX-MIA-FRZ-32", "outcome": "YES"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SETTLEMENT_RESOLVED"
    assert data["settlement"]["contract_ticker"] == "KX-MIA-FRZ-32"
    assert data["settlement"]["outcome"] == "YES"
    assert "STL-" in data["settlement"]["settlement_id"]

def test_dashboard_ui_contains_settlement_reconciler_elements():
    res = client.get("/dashboard")
    assert res.status_code == 200
    html = res.text
    assert 'id="settle-modal"' in html
    assert "SETTLEMENT RECONCILER" in html
    assert "openSettleModal" in html
    assert "executeSettlement" in html
