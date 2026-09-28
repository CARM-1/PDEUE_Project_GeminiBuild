"""Wave 2B Class H lineage desk authorization and governance contracts."""
from fastapi.testclient import TestClient

from app.api.v1 import portal_router
from app.main import app


CLIENT = TestClient(app)


def test_lineage_portal_h2_renders_breakers_and_voting_chamber():
    response = CLIENT.get("/lineage/house/2?role=H2", headers={"X-House-ID": "2"})
    assert response.status_code == 200
    assert "Active Hat: HOUSE_LEADER (H2_SOVEREIGN)" in response.text
    assert "Freeze Dial (0%)" in response.text and "Cancel Orders" in response.text
    assert "Bicameral CFCP Ratification Chamber" in response.text
    assert 'id="vote-aye"' in response.text and 'id="vote-nay"' in response.text


def test_lineage_portal_h1_strips_breakers_and_masks_balances():
    response = CLIENT.get("/lineage/house/2?role=H1", headers={"X-House-ID": "HOUSE-02"})
    assert response.status_code == 200
    assert "Active Hat: HOUSE_ASSISTANT (H1_SECRETARIAL)" in response.text
    assert "$****.**" in response.text
    assert "Freeze Dial (0%)" not in response.text and "Cancel Orders</button>" not in response.text
    assert 'id="vote-aye"' not in response.text and 'id="vote-nay"' not in response.text
    assert "NON-VOTING AUDIT" in response.text and "Meeting Scheduler" in response.text
    state = CLIENT.get("/api/v1/portal/lineage/house/2/state?role=H1", headers={"X-House-ID": "2"}).json()
    assert all(member["notional_cents"] == "$****.**" for member in state["members"])
    assert isinstance(state["aggregated_house_capital_cents"], int)


def test_lineage_h1_vote_attempt_returns_403_forbidden():
    response = CLIENT.post(
        "/api/v1/portal/lineage/house/2/vote?role=H1",
        headers={"X-House-ID": "2"}, json={"proposal_id": "CFCP-2026-02", "vote": "AYE"},
    )
    assert response.status_code == 403


def test_lineage_h1_circuit_breaker_attempt_returns_403_forbidden():
    response = CLIENT.post(
        "/api/v1/portal/lineage/house/2/circuit-breaker?role=H1",
        headers={"X-House-ID": "2"}, json={"scma_id": "SCMA-JULIAN_-A1F98B21", "action": "FREEZE_DIAL"},
    )
    assert response.status_code == 403


def test_cross_house_isolation_blocks_unauthorized_inspection():
    assert CLIENT.get("/lineage/house/2?role=H2", headers={"X-House-ID": "1"}).status_code == 403
    assert CLIENT.get("/api/v1/portal/lineage/house/2/state", headers={"X-House-ID": "HOUSE-01"}).status_code == 403


def test_bicameral_vote_reaches_supermajority_threshold_and_stages_settlor_petition():
    proposal = portal_router._LINEAGE_PROPOSALS["CFCP-2026-02"]
    proposal.update(aye_house_ids=[], nay_house_ids=[], status="HOUSE_VOTE_OPEN")
    result = None
    for house_id in range(1, 10):
        result = CLIENT.post(
            f"/api/v1/portal/lineage/house/{house_id}/vote?role=H2",
            headers={"X-House-ID": str(house_id)}, json={"proposal_id": "CFCP-2026-02", "vote": "AYE"},
        )
        assert result.status_code == 200
    assert result is not None
    assert result.json()["aye_count"] == 9
    assert result.json()["status"] == "RATIFIED_PENDING_SETTLOR"
    assert result.json()["effect"] == "ADVISORY_PETITION_ONLY"
