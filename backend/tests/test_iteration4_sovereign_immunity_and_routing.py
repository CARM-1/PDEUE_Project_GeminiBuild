from fastapi.testclient import TestClient

from app.api.v1.lineage_router import _lineage_service
from app.main import app


client = TestClient(app)


def test_house_freeze_clamps_eleanor_but_preserves_founder():
    house = _lineage_service.CANONICAL_HOUSES[1]
    founder, eleanor = house["members"]
    _lineage_service.restore_house(1)
    founder["risk_dial"] = 0.02
    founder["open_orders"] = ["KX-MIA-FRZ-32"]

    response = client.post("/api/v1/lineage/house/1/freeze")

    assert response.status_code == 200
    assert founder["status"] == "ACTIVE"
    assert founder["risk_dial"] == 0.02
    assert founder["open_orders"] == ["KX-MIA-FRZ-32"]
    assert eleanor["risk_dial"] == 0.0
    assert eleanor["status"] == "FROZEN_BY_HOUSE_QUARANTINE"


def test_member_state_routes_to_julian():
    julian = _lineage_service.CANONICAL_HOUSES[2]["members"][0]
    julian["open_orders"] = ["POLY-239496"]
    response = client.get(
        "/api/v1/portal/member/state",
        params={"scma_id": "SCMA-JULIAN_-A1F98B21"},
    )

    assert response.status_code == 200
    assert response.json()["scma_id"] == "SCMA-JULIAN_-A1F98B21"
    assert response.json()["name"] == "Julian Vance (Apprentice)"
    assert response.json()["cash_balance"] == 250.0
    assert response.json()["open_orders"] == ["POLY-239496"]


def test_quarantine_is_inherited_by_eleanor_portal_state():
    _lineage_service.freeze_house(1)

    response = client.get(
        "/api/v1/portal/member/state",
        params={"scma_id": "SCMA-ELEANOR_-B2B31C9E"},
    )

    assert response.status_code == 200
    assert response.json()["parent_house_status"] == "QUARANTINED"
