import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.domain.quarter_kelly_dispatcher import QuarterKellyDispatcher

client = TestClient(app)

def test_quarter_kelly_sizing_calculation():
    disp = QuarterKellyDispatcher(kelly_fraction=0.25)
    # 31.5% model probability vs 3.0% market price on $5,000 SCMA (500,000 cents)
    # Risk dial: 2.0% (0.02)
    res = disp.calculate_sizing(
        model_prob=0.315,
        market_price=0.03,
        available_cash_cents=500000,
        risk_dial=0.02
    )

    assert res["net_edge"] == 0.285
    assert res["full_kelly"] > 0.25
    assert res["quarter_kelly"] > 0.05
    assert res["effective_fraction"] == 0.02
    # Discrete sizing: 10,000 cents // 3 cents = 3,333 contracts = 9,999 cents
    assert res["contract_quantity"] == 3333
    assert res["unit_cost_cents"] == 3
    assert res["stake_cents"] == 9999

def test_negative_edge_blocks_allocation():
    disp = QuarterKellyDispatcher()
    res = disp.calculate_sizing(
        model_prob=0.40,
        market_price=0.45,
        available_cash_cents=100000,
        risk_dial=0.02
    )
    assert res["stake_cents"] == 0
    assert res["contract_quantity"] == 0
    assert res["reason"] == "NEGATIVE_EDGE"

def test_stage_order_api_endpoint_house_dispatch():
    payload = {
        "contract_ticker": "KX-MIA-FRZ-32",
        "venue": "KALSHI",
        "target_house_id": 1,
        "side": "BUY_YES",
        "market_price": 0.03,
        "model_prob": 0.315
    }
    res = client.post("/api/v1/operator/stage-order", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ORDER_STAGED"
    
    dispatch = data["dispatch"]
    assert dispatch["lineage_code"] == "HOUSE-01"
    assert dispatch["status"] == "RESTING_MAKER"
    assert dispatch["total_quantity"] > 0
    assert len(dispatch["member_allocations"]) == 2  # Founder + Eleanor in House 1

def test_stage_order_invalid_house_id_rejection():
    res = client.post("/api/v1/operator/stage-order", json={"target_house_id": 13})
    assert res.status_code == 400
    assert "House ID must be between 1 and 12" in res.json()["detail"]
