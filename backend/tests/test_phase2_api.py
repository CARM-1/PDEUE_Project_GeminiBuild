from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.api.v1.phase2_routes import router as phase2_router

app.include_router(phase2_router)
client = TestClient(app)

def test_authenticated_phase2_evaluate():
    token = create_access_token({"sub": "usr_123", "account_id": "acc_456", "role": "TRADER"})
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "station_id": "KORD",
        "temp_c": 26.5,
        "timestamp": "2026-09-02T18:00:00Z",
        "ticker": "KXCHICAGO-26SEP02",
        "yes_bid": 0.40,
        "yes_ask": 0.45
    }
    response = client.post("/api/v1/phase2/evaluate", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["recommended_action"] == "BUY_YES"
    assert data["tenant_context"]["user_id"] == "usr_123"
    assert data["tenant_context"]["account_id"] == "acc_456"
