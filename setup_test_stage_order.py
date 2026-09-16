import pathlib

test_file = pathlib.Path("backend/tests/test_stage_order.py")
test_file.write_text('''import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_stage_limit_order():
    payload = {
        "contract_id": "KX-MIA-FRZ-32",
        "venue": "KALSHI",
        "side": "BUY",
        "quantity": 5000,
        "price": 0.02,
        "member_id": "FOUNDER_SCMA",
        "dossier_id": "DOS-TEST-001"
    }
    response = client.post("/api/v1/operator/stage-order", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["staged_order"]["contract_id"] == "KX-MIA-FRZ-32"
    assert data["staged_order"]["status"] == "STAGED_RESTING"
    assert data["staged_order"]["reserved_cents"] == 10000
    assert data["active_reservation_cents"] >= 10000
''', encoding="utf-8")
print(f"Created {test_file}")