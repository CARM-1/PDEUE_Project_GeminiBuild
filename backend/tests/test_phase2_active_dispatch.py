import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_stage_order_commits_to_active_portfolio_ledger():
    payload = {
        "contract_ticker": "KX-MIA-FRZ-32",
        "venue": "KALSHI",
        "target_house_id": 1,
        "side": "BUY_YES",
        "market_price": 0.03,
        "model_prob": 0.315
    }

    # 1. Dispatch Order
    res = client.post("/api/v1/operator/stage-order", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ORDER_STAGED"
    assert data["dispatch"]["lineage_code"] == "HOUSE-01"

    # 2. Inspect Operator Workspace State (Tab 1 Active Ledger Sync)
    state_res = client.get("/api/v1/operator/workspace-state")
    assert state_res.status_code == 200
    state = state_res.json()

    positions = state.get("positions", [])
    staged_matches = [p for p in positions if p.get("contract") == "KX-MIA-FRZ-32"]
    assert len(staged_matches) >= 1
    committed = staged_matches[0]
    assert committed["status"] == "RESTING_MAKER"
    assert committed["lineage_code"] == "HOUSE-01"
    assert committed["venue"] == "KALSHI"

def test_dashboard_contains_stage_house_dispatch_client():
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "stageHouseDispatch" in res.text
    assert "/api/v1/operator/stage-order" in res.text
