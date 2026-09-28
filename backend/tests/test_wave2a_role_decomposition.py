"""Wave 2A sub-tier authorization and browser-rendering contract tests."""
from fastapi.testclient import TestClient

from app.api.v1 import portal_router
from app.main import app

CLIENT = TestClient(app)


def test_tech_console_t1_strips_triggers_and_override():
    page = CLIENT.get("/admin/tech?tier=T1").text
    telemetry = CLIENT.get("/api/v1/portal/tech/telemetry?tier=T1").json()
    assert "T1_MONITOR" in page and "activeTier==='T1'" in page
    assert telemetry["can_trigger_daemons"] is False
    assert telemetry["can_override_redaction"] is False
    assert CLIENT.post("/api/v1/portal/tech/trigger-daemon?tier=T1").status_code == 403
    assert CLIENT.post("/api/v1/portal/tech/ca-override?tier=T1", json={"token": "CA-OVERRIDE-SECRET-DEV"}).status_code == 403


def test_tech_console_t2_enables_triggers_blocks_override():
    telemetry = CLIENT.get("/api/v1/portal/tech/telemetry?tier=T2").json()
    assert telemetry["can_trigger_daemons"] is True
    assert telemetry["can_override_redaction"] is False
    assert CLIENT.post("/api/v1/portal/tech/trigger-daemon?tier=T2").status_code == 200
    assert CLIENT.post("/api/v1/portal/tech/ca-override?tier=T2", json={"token": "CA-OVERRIDE-SECRET-DEV"}).status_code == 403


def test_tech_console_t3_full_operational_access():
    telemetry = CLIENT.get("/api/v1/portal/tech/telemetry?tier=T3").json()
    assert telemetry["can_trigger_daemons"] is True
    assert telemetry["can_override_redaction"] is True
    assert telemetry["active_order_ladder"][0]["exposure_cents"] == "$****.**"
    override = CLIENT.post("/api/v1/portal/tech/ca-override?tier=T3", json={"token": "CA-OVERRIDE-SECRET-DEV"})
    assert override.status_code == 200 and override.json()["redaction_active"] is False


def test_advisor_f1_restricts_equity_and_hides_co_sign_queue():
    scoped = CLIENT.get("/api/v1/portal/advisor/household-tree?role=F1").json()
    assert [account["name"] for account in scoped["accounts"]] == ["Julian Vance (Apprentice)"]
    assert "total_family_equity_cents" not in scoped
    assert "available_liquidity_cents" not in scoped
    assert scoped["pending_distributions"] == []
    assert "F1 RESTRICTED - MENTEE VIEW ONLY" in CLIENT.get("/advisor").text


def test_advisor_f2h_renders_full_domestic_queue_and_co_sign():
    portal_router._DISTRIBUTION_STATE["DIST-104"].update(status="PENDING", signature=None)
    scoped = CLIENT.get("/api/v1/portal/advisor/household-tree?role=F2-H").json()
    assert len(scoped["accounts"]) == 3
    assert scoped["total_family_equity_cents"] == 650000
    assert scoped["pending_distributions"][0]["action"] == "F2_CO_SIGN"
    assert CLIENT.post("/api/v1/portal/advisor/co-sign", json={"request_id": "DIST-104", "actor_role": "F2-H"}).status_code == 200


def test_advisor_f2a_and_f3_read_only_co_sign_boundaries():
    for role in ("F2-A", "F3"):
        scoped = CLIENT.get(f"/api/v1/portal/advisor/household-tree?role={role}").json()
        assert all(item["action"] == "READ_ONLY_AUDIT" for item in scoped["pending_distributions"])
        denied = CLIENT.post("/api/v1/portal/advisor/co-sign", json={"request_id": "DIST-105", "actor_role": role})
        assert denied.status_code == 403
    assert "platform_risk_metrics" in CLIENT.get("/api/v1/portal/advisor/household-tree?role=F3").json()
