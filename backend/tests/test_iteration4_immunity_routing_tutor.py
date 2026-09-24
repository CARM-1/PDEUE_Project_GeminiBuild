from fastapi.testclient import TestClient

from app.api.v1.lineage_router import _lineage_service
from app.main import app


client = TestClient(app)


def test_founder_risk_dial_is_immune_to_house_freeze():
    _lineage_service.restore_house(1)
    founder = _lineage_service.CANONICAL_HOUSES[1]["members"][0]
    original_dial = founder["risk_dial"]

    response = client.post("/api/v1/lineage/house/1/freeze")

    assert response.status_code == 200
    assert founder["risk_dial"] == original_dial
    assert founder["status"] == "ACTIVE"


def test_member_state_can_route_by_scma_id():
    response = client.get(
        "/api/v1/portal/member/state",
        params={"scma_id": "SCMA-JULIAN_-A1F98B21"},
    )

    assert response.status_code == 200
    state = response.json()
    assert state["name"].startswith("Julian Vance")
    assert state["cash_balance"] == 250.0
    assert state["parent_house_status"] in {"ACTIVE", "QUARANTINED"}
    assert "open_orders" in state


def test_ai_tutor_gives_substantive_waterfall_explanation():
    response = client.post(
        "/api/v1/portal/member/ai-tutor",
        json={"query": "How does the waterfall split work?"},
    )

    assert response.status_code == 200
    answer = response.json()["response"]
    assert len(answer.split(". ")) >= 4
    for concept in ("87%", "SCMA", "10%", "CFCP", "3%", "FAEP"):
        assert concept in answer


def test_dashboard_contains_sovereign_badge_and_member_link_template():
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "🛡️ Sovereign Immune" in response.text
    assert '<a href="/member?scma=${member.scma_id}"' in response.text
