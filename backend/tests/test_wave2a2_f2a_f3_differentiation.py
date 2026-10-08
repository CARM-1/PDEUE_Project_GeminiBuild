"""Wave 2A.2 fiduciary proposal and macro-CRO acceptance contracts."""
from fastapi.testclient import TestClient

from app.api.v1 import portal_router
from app.main import app

CLIENT = TestClient(app)


def test_f3_cro_renders_macro_risk_and_strips_domestic_household_cards():
    page = CLIENT.get("/advisor?role=F3").text
    assert "Global 99% VaR Gauge" in page
    assert "Cross-House Gross Margin" in page
    assert "Venue Exposure Balance" in page
    assert "Directive R-04 Emergency Financial Halt" in page
    risk = CLIENT.get("/api/v1/portal/advisor/macro-risk?role=F3").json()
    assert risk["platform_var_99_24h_cents"] == 42_000
    assert len(risk["house_exposures"]) == 12
    scoped = CLIENT.get("/api/v1/portal/advisor/household-tree?role=F3").json()
    assert scoped["accounts"] == [] and "total_family_equity_cents" not in scoped


def test_f3_cro_supervisory_queue_has_approve_and_deny_actions():
    page = CLIENT.get("/advisor?role=F3").text
    assert "Fiduciary Supervisory Queue" in page
    assert "Approve Proposal" in page and "Veto Proposal" in page


def test_f2a_renders_household_selector_and_stage_proposal_controls():
    page = CLIENT.get("/advisor?role=F2-A").text
    assert 'id="household-selector"' in page
    assert "HOUSEHOLD-ALPHA" in page and "HOUSEHOLD-BETA" in page
    assert "Stage Advisory Proposal" in page
    assert "READ-ONLY AUDIT: F2-H SIGNATURE REQUIRED" in page


def _stage_proposal() -> str:
    response = CLIENT.post(
        "/api/v1/portal/advisor/proposals?role=F2-A",
        json={"target_scma": "SCMA-JULIAN_-A1F98B21", "proposed_dial": 1.25,
              "justification": "Reduce concentration while preserving the capital floor."},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING"
    return response.json()["proposal_id"]


def test_f2a_cannot_adjudicate_proposals_returns_403():
    proposal_id = _stage_proposal()
    denied = CLIENT.post(
        f"/api/v1/portal/advisor/proposals/{proposal_id}/adjudicate?role=F2-A",
        json={"decision": "ALLOW"},
    )
    assert denied.status_code == 403


def test_f3_adjudicates_proposal_successfully_mutating_state():
    proposal_id = _stage_proposal()
    allowed = CLIENT.post(
        f"/api/v1/portal/advisor/proposals/{proposal_id}/adjudicate?role=F3",
        json={"decision": "ALLOW"},
    )
    assert allowed.status_code == 200 and allowed.json()["status"] == "ALLOWED"
    ledger = CLIENT.get("/api/v1/portal/advisor/proposals?role=F3").json()["proposals"]
    assert next(item for item in ledger if item["proposal_id"] == proposal_id)["status"] == "ALLOWED"


def test_f3_and_f2a_blocked_from_co_signing_domestic_living_expenses():
    portal_router._DISTRIBUTION_STATE["DIST-105"].update(status="PENDING", signature=None)
    for role in ("F2-A", "F3"):
        response = CLIENT.post(
            "/api/v1/portal/advisor/co-sign",
            json={"request_id": "DIST-105", "actor_role": role},
        )
        assert response.status_code == 403
    assert portal_router._DISTRIBUTION_STATE["DIST-105"]["status"] == "PENDING"


def test_legacy_portal_hub_preserved():
    assert '<div style="display:none" id="legacyPortalHub">' in CLIENT.get("/advisor").text
