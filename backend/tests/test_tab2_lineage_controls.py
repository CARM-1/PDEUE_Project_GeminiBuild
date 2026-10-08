from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.lineage_router import _lineage_service


client = TestClient(app)
SCMA = "SCMA-FOUNDER_-C8575D7E"


def test_dashboard_contains_dynamic_twelve_house_lineage_tree():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert 'id="lineage-house-tree-container"' in response.text
    assert 'data-house-count="12"' in response.text
    assert "12-House Master-Detail Lineage Tree" in response.text
    assert "/api/v1/lineage/house/${houseId}/subordinate/${action}" in response.text


def test_freeze_risk_preserves_sovereign_dial():
    member = _lineage_service.CANONICAL_HOUSES[1]["members"][0]
    member["risk_dial"] = 0.02
    member["status"] = "ACTIVE"
    response = client.post(
        "/api/v1/lineage/house/1/subordinate/freeze-risk",
        json={"scma_id": SCMA},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "SOVEREIGN_IMMUNE"
    assert response.json()["new_risk_dial"] == 0.02
    assert member["risk_dial"] == 0.02


def test_cancel_orders_preserves_sovereign_orders():
    member = _lineage_service.CANONICAL_HOUSES[1]["members"][0]
    member["open_orders"] = ["KX-MIA-FRZ-32"]
    response = client.post(
        "/api/v1/lineage/house/1/subordinate/cancel-orders",
        json={"scma_id": SCMA},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "SOVEREIGN_IMMUNE"
    assert response.json()["cancelled_orders"] == []
    assert member["open_orders"] == ["KX-MIA-FRZ-32"]
