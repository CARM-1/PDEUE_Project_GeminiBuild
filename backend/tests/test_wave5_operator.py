from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "HEALTHY"

def test_paper_session_flow():
    res = client.post("/api/v1/paper/sessions", json={"initial_capital_cents": 100000})
    assert res.status_code == 200
    session = res.json()
    session_id = session["session_id"]
    assert session["available_capital_cents"] == 100000

    trade_res = client.post("/api/v1/paper/trade", json={
        "session_id": session_id,
        "contract_id": "CT-WX-01",
        "price": 0.45,
        "quantity": 1000
    })
    assert trade_res.status_code == 200
    assert trade_res.json()["status"] == "EXECUTED"
    assert trade_res.json()["remaining_capital_cents"] == 55000

    over_res = client.post("/api/v1/paper/trade", json={
        "session_id": session_id,
        "contract_id": "CT-WX-01",
        "price": 0.90,
        "quantity": 1000
    })
    assert over_res.status_code == 200
    assert over_res.json()["status"] == "REJECTED"
