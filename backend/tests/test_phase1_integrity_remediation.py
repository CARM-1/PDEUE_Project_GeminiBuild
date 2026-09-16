import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_admin_tech_clean_template():
    res = client.get("/admin/tech")
    assert res.status_code == 200
    # Must contain Technical Console elements
    assert "PDEUE Technical Infrastructure Console" in res.text
    # Must NOT contain contaminated advisor elements
    assert "Financial Advisor Workspace" not in res.text
    assert "FOUNDER SCMA POOL" not in res.text
    assert "Trustee Quorum & Fiduciary Invariants" not in res.text

def test_dashboard_supervisory_lens_and_lineage_aggregate():
    res = client.get("/dashboard")
    assert res.status_code == 200
    # Supervisory Lens dropdown must exist
    assert "SUPERVISORY LENS:" in res.text
    assert "/admin/tech" in res.text
    assert "/advisor" in res.text
    # Tab 1 should reflect Lineage Overview rather than Founder SCMA
    assert "1. Lineage Executive Overview" in res.text
    assert "LINEAGE TOTAL EQUITY" in res.text

def test_member_split_hat_role_presentation():
    # When Eleanor Vance checks /member, her role is MEMBER_USER
    res = client.get("/api/v1/portal/member/state?user_id=USR-eleanor_va-B2B31C9E")
    assert res.status_code == 200
    assert res.json()["role"] == "MEMBER_USER"

    # When Founder checks /member, personal role is also MEMBER_USER
    res_f = client.get("/api/v1/portal/member/state?user_id=USR-founder_ch-C8575D7E")
    assert res_f.status_code == 200
    assert res_f.json()["role"] == "MEMBER_USER"
    assert res_f.json()["cash_balance"] == 5000.00

def test_option_a_waterfall_invariants():
    res = client.get("/api/v1/portal/member/state")
    assert res.status_code == 200
    w = res.json()["waterfall_structure"]
    assert w["scma_compounding_pct"] == 87.0
    assert w["cfcp_lineage_shield_pct"] == 10.0
    assert w["faep_endowment_pct"] == 3.0
    assert "Option A" in w["rule"]
