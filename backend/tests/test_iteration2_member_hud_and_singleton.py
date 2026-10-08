from fastapi.testclient import TestClient

from app.domain.lineage_hierarchy import get_lineage_service
from app.main import app


client = TestClient(app)
ELEANOR_SCMA = "SCMA-ELEANOR_-B2B31C9E"


def test_lineage_freeze_is_immediately_shared_with_workspace_and_member_portal():
    member = next(
        item
        for item in get_lineage_service().CANONICAL_HOUSES[1]["members"]
        if item["scma_id"] == ELEANOR_SCMA
    )
    previous_risk, previous_status = member["risk_dial"], member["status"]
    try:
        response = client.post(
            "/api/v1/lineage/house/1/subordinate/freeze-risk",
            json={"scma_id": ELEANOR_SCMA},
        )
        assert response.status_code == 200

        workspace = client.get("/api/v1/operator/workspace-state").json()
        workspace_member = next(
            item
            for house in workspace["houses"]
            for item in house["members"]
            if item["scma_id"] == ELEANOR_SCMA
        )
        assert workspace_member["risk_dial"] == 0.0
        assert workspace_member["status"] == "FROZEN_BY_HOUSE_LEADER"

        portal = client.get("/api/v1/portal/member/state").json()
        assert portal["scma_id"] == ELEANOR_SCMA
        assert portal["risk_dial_pct"] == 0.0
        assert portal["status"] == "FROZEN_BY_HOUSE_LEADER"
    finally:
        member["risk_dial"], member["status"] = previous_risk, previous_status


def test_member_page_contains_dynamic_hud_controls_and_trajectory_canvas():
    response = client.get("/member")
    assert response.status_code == 200
    assert "My Trajectory" in response.text
    assert "Asset Engine Rings" in response.text
    assert "High-Yield Radar" in response.text
    assert 'id="trajectory-canvas"' in response.text
    assert "setInterval(loadState, 3000)" in response.text
