import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.domain.lineage_hierarchy import LineageHierarchyService

client = TestClient(app)

def test_house_petition_intake_requires_75_percent_for_review():
    svc = LineageHierarchyService()
    # 8 votes = 66.7% -> Quorum rejected
    p1 = svc.submit_house_petition("Title A", "Desc", 2, 10000, [1, 2, 3, 4, 5, 6, 7, 8])
    assert p1["house_ratified"] is False
    assert p1["status"] == "QUORUM_REJECTED"

    # 9 votes = 75.0% -> Eligible for Founder review
    p2 = svc.submit_house_petition("Title B", "Desc", 2, 10000, [1, 2, 3, 4, 5, 6, 7, 8, 9])
    assert p2["house_ratified"] is True
    assert p2["status"] == "PENDING_CHIEF_ADMIN_AUTHORIZATION"

def test_unanimous_house_vote_cannot_execute_without_founder():
    svc = LineageHierarchyService()
    # 12 of 12 Houses vote yes
    p = svc.submit_house_petition("Raid CFCP", "Desc", 2, 500000, list(range(1, 13)))
    assert p["house_ratified"] is True
    # Still pending! Cannot execute on its own
    assert p["status"] == "PENDING_CHIEF_ADMIN_AUTHORIZATION"

def test_sovereign_settlor_unilateral_veto_overrides_unanimous_vote():
    svc = LineageHierarchyService()
    # Unanimous 12-House petition
    p = svc.submit_house_petition("High Risk Proposal", "Desc", 2, 200000, list(range(1, 13)))
    pid = p["proposal_id"]

    # Founder exercises Sovereign Veto
    vetoed = svc.adjudicate_proposal(pid, "SOVEREIGN_VETO", "SCMA-FOUNDER_-C8575D7E")
    assert vetoed["status"] == "SOVEREIGN_VETOED"
    assert vetoed["settled_by"] == "SCMA-FOUNDER_-C8575D7E"

def test_non_founder_cannot_adjudicate_proposals():
    svc = LineageHierarchyService()
    p = svc.submit_house_petition("House Grant", "Desc", 2, 50000, list(range(1, 10)))
    pid = p["proposal_id"]

    # Subordinate member attempts to approve
    with pytest.raises(PermissionError):
        svc.adjudicate_proposal(pid, "APPROVE_AND_EXECUTE", "SCMA-JULIAN_-A1F98B21")

def test_api_sovereign_governance_flow():
    # 1. Fetch proposals
    res = client.get("/api/v1/lineage/governance/proposals")
    assert res.status_code == 200
    assert len(res.json()["proposals"]) >= 1

    # 2. Founder approves seed proposal
    res_adj = client.post(
        "/api/v1/lineage/governance/adjudicate",
        json={
            "proposal_id": "PROP-2026-001",
            "action": "APPROVE_AND_EXECUTE",
            "caller_scma": "SCMA-FOUNDER_-C8575D7E"
        }
    )
    assert res_adj.status_code == 200
    assert res_adj.json()["status"] == "SOVEREIGN_EXECUTED"

def test_tab4_ui_contains_sovereign_settlor_elements():
    res = client.get("/dashboard")
    assert res.status_code == 200
    html = res.text
    assert "SOVEREIGN SETTLOR JURISDICTION" in html
    assert "FOUNDER VETO: ACTIVE" in html
    assert "IMMUTABLE ARCHITECTURAL INVARIANTS" in html
    assert "87 / 10 / 3 Waterfall" in html
