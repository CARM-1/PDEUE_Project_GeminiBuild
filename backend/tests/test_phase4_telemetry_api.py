from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_jwt_token

client = TestClient(app)

def test_operator_paper_session_and_audit_api():
    token = create_jwt_token({"tenant_id": "tenant_admin", "user_id": "admin_01"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/v1/operator/paper/start", json={"initial_capital": 250000.0}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["session"]["current_balance"] == 250000.0
    audit_res = client.get("/api/v1/operator/audit/logs", headers=headers)
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert audit_data["audit_count"] >= 1
    assert audit_data["logs"][0]["action"] == "SESSION_STARTED"
