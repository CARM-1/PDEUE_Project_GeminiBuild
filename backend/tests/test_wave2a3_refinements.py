"""Wave 2A.3 console, supervisory queue, and educational depth contracts."""
from fastapi.testclient import TestClient

from app.api.v1 import portal_router
from app.domain.ai_copilot import AICopilotEngine
from app.main import app


CLIENT = TestClient(app)


def test_admin_tech_renders_dual_daemons_and_red_override_button():
    page = CLIENT.get("/admin/tech?tier=T3").text
    assert "AutonomousScanWorker" in page
    assert "Cycle 0 · ACTIVE" in page
    assert "Trigger Scan Cycle" in page
    assert "SettlementReconciler" in page
    assert "Waterfall: 87/10/3" in page
    assert "Trigger Settlement" in page
    assert "override-alert" in page
    assert "background:#ef4444;color:white" in page
    assert page.index("Authenticate CA Override") < page.index("Recent Dispatches")
    assert "$('grant').hidden=activeTier!=='T3'" in page


def test_f3_renders_seeded_proposal_with_approve_veto_buttons():
    proposal = portal_router._ADVISORY_PROPOSALS["PROP-ADV-01"]
    proposal.update(status="PENDING", adjudicated_by=None)
    page = CLIENT.get("/advisor?role=F3").text
    ledger = CLIENT.get("/api/v1/portal/advisor/proposals?role=F3").json()["proposals"]
    seeded = next(item for item in ledger if item["proposal_id"] == "PROP-ADV-01")
    assert seeded["target_scma"] == "SCMA-JULIAN"
    assert seeded["sponsor"] == "F2-A Vance"
    assert seeded["justification"] == "Candidate completed Binary 101."
    assert "Sponsor:" in page and "Justification:" in page
    assert "Approve Proposal" in page and "Veto Proposal" in page

    approved = CLIENT.post(
        "/api/v1/portal/advisor/proposals/PROP-ADV-01/adjudicate?role=F3",
        json={"decision": "ALLOW"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED / ACTIVE"
    assert portal_router._ADVISORY_PROPOSALS["PROP-ADV-01"]["status"] == "APPROVED / ACTIVE"


def test_ai_copilot_returns_deep_novice_explanation():
    engine = AICopilotEngine()
    response = engine.process_query("Explain the 87/10/3 waterfall simply for a novice")
    text = response["response_text"]
    assert all(term in text for term in ("87%", "SCMA", "10%", "FSAP", "3%", "Stewardship"))
    assert "never from member pockets" in text
    assert "never deducted on losing trades" in text
    assert response["lineage_context"]["audience"] == "NOVICE"
