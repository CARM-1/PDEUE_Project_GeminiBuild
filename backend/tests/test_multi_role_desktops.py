from fastapi.testclient import TestClient
try:
    from backend.app.main import app
except ImportError:
    from app.main import app

client = TestClient(app)

def test_portal_html_routes_render():
    res_m = client.get("/member")
    assert res_m.status_code == 200
    assert "Member User Desktop" in res_m.text

    res_a = client.get("/advisor")
    assert res_a.status_code == 200
    assert "Financial Advisor Workspace" in res_a.text

    res_t = client.get("/admin/tech")
    assert res_t.status_code == 200
    assert "Technical Infrastructure Console" in res_t.text

def test_member_risk_dial_downward_only():
    # Valid downward adjust
    res = client.post("/api/v1/portal/member/SCMA-MEM-001/risk-dial", json={"new_risk_dial": 2.0})
    assert res.status_code == 200
    assert res.json()["applied_risk_dial"] == 2.0

    # Unauthorized upward adjust (ceiling is 3.0%)
    res_up = client.post("/api/v1/portal/member/SCMA-MEM-001/risk-dial", json={"new_risk_dial": 4.5})
    assert res_up.status_code == 403

    # Out of range adjust
    res_oor = client.post("/api/v1/portal/member/SCMA-MEM-001/risk-dial", json={"new_risk_dial": 6.0})
    assert res_oor.status_code == 400

def test_advisor_read_only_and_audit():
    res = client.get("/api/v1/portal/advisor/households")
    assert res.status_code == 200
    data = res.json()
    assert len(data["members"]) == 2

    res_audit = client.get("/api/v1/portal/advisor/decision-audit/IF-037-CONTRACT-DEMO")
    assert res_audit.status_code == 200
    assert "plain_english_rationale" in res_audit.json()

def test_ai_tutor_answers():
    res = client.post("/api/v1/portal/member/ai-tutor", json={"question": "How does compounding work?"})
    assert res.status_code == 200
    assert "87%" in res.json()["answer"]
