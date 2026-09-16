import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.v1.portal_router import LINEAGE_DATA

client = TestClient(app)

def test_html_portal_routes_render():
    for route in ["/member", "/advisor", "/admin/tech"]:
        res = client.get(route)
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]

def test_member_isolation_and_custodial_flag():
    # Regular member
    res = client.get("/api/v1/portal/member/state?user_id=USR-eleanor_va-B2B31C9E")
    assert res.status_code == 200
    data = res.json()
    assert data["scma_id"] == "SCMA-ELEANOR_-B2B31C9E"
    assert data["is_custodial"] is False
    assert "cfcp_floor_shield" not in data  # No master pool leakage

    # Custodial member
    res_cust = client.get("/api/v1/portal/member/state?user_id=USR-julian_va-A1F98B21")
    assert res_cust.status_code == 200
    cust_data = res_cust.json()
    assert cust_data["is_custodial"] is True
    assert cust_data["custodian_id"] == "USR-eleanor_va-B2B31C9E"

def test_custodial_risk_lock_rejection():
    # Attempting to modify risk dial on custodial account must fail with 403 Forbidden
    res = client.post(
        "/api/v1/portal/member/SCMA-JULIAN_-A1F98B21/risk-dial",
        json={"requested_risk_pct": 0.8}
    )
    assert res.status_code == 403
    assert "Custodial Account: Risk adjustments locked" in res.json()["detail"]

def test_downward_only_risk_rule():
    # Eleanor's current risk is 1.5%. Attempting to increase to 1.8% must fail
    res_up = client.post(
        "/api/v1/portal/member/SCMA-ELEANOR_-B2B31C9E/risk-dial",
        json={"requested_risk_pct": 1.8}
    )
    assert res_up.status_code == 400
    assert "Downward-only policy" in res_up.json()["detail"]

    # Reducing to 1.2% must be approved
    res_down = client.post(
        "/api/v1/portal/member/SCMA-ELEANOR_-B2B31C9E/risk-dial",
        json={"requested_risk_pct": 1.2}
    )
    assert res_down.status_code == 200
    assert res_down.json()["applied_risk_dial"] == 1.2

def test_advisor_lineage_supervision():
    res = client.get("/api/v1/portal/advisor/lineage?household_id=HOUSEHOLD-ALPHA")
    assert res.status_code == 200
    data = res.json()
    assert data["household_id"] == "HOUSEHOLD-ALPHA"
    assert len(data["sub_accounts"]) == 3
    assert len(data["audit_queue"]) >= 1

def test_directive_r12_tech_telemetry_redaction():
    # Normal view must redact identifiers and cents
    res = client.get("/api/v1/portal/tech/telemetry")
    assert res.status_code == 200
    d = res.json()
    assert d["redaction_active"] is True
    assert d["recent_dispatches"][0]["account_id"] == "SCMA-MEM-****-REDACTED"
    assert d["recent_dispatches"][0]["notional_cents"] == "REDACTED"

    # Authorized CA Override view unmasks operational data plane
    res_unredact = client.get("/api/v1/portal/tech/telemetry?unredact_token=AUTH-CA-OVERRIDE-TEMP")
    assert res_unredact.status_code == 200
    d_un = res_unredact.json()
    assert d_un["redaction_active"] is False
    assert "SCMA-ELEANOR" in d_un["recent_dispatches"][0]["account_id"]
    assert d_un["recent_dispatches"][0]["notional_cents"] == 2500
