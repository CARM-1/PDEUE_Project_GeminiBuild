import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_portal_html_renders_without_hub_leak():
    for route in ["/member", "/advisor", "/admin/tech"]:
        res = client.get(route)
        assert res.status_code == 200
        # Assert the boundary leak ribbon is NOT present
        assert "PDEUE PORTAL HUB:" not in res.text

def test_three_tier_distribution_gateway():
    # Green Tier (< $100) -> Autonomous
    res_green = client.post("/api/v1/portal/member/request-distribution", json={
        "scma_id": "SCMA-ELEANOR_-B2B31C9E",
        "amount_cents": 5000,
        "category_tag": "Personal"
    })
    assert res_green.status_code == 200
    assert res_green.json()["tier"] == "GREEN"
    assert res_green.json()["status"] == "EXECUTED_AUTONOMOUS"

    # Red Tier (> $500) -> 24h Cooling Off & F2 Co-signature
    res_red = client.post("/api/v1/portal/member/request-distribution", json={
        "scma_id": "SCMA-ELEANOR_-B2B31C9E",
        "amount_cents": 65000,
        "category_tag": "Tuition"
    })
    assert res_red.status_code == 200
    assert res_red.json()["tier"] == "RED"
    assert res_red.json()["status"] == "PENDING_F2_COSIGN"

def test_advisor_tier_adaptation():
    # F1 Peer Guide: Scoped to mentee only
    r_f1 = client.get("/api/v1/portal/advisor/lineage?tier=F1")
    assert r_f1.status_code == 200
    assert len(r_f1.json()["sub_accounts"]) == 1
    assert r_f1.json()["macro_risk"] is None

    # F2 Household Lead: Full household + approval queue
    r_f2 = client.get("/api/v1/portal/advisor/lineage?tier=F2")
    assert r_f2.status_code == 200
    assert len(r_f2.json()["sub_accounts"]) == 3
    assert len(r_f2.json()["pending_approvals"]) == 1

    # F3 CRO: Platform-wide factor risk matrix
    r_f3 = client.get("/api/v1/portal/advisor/lineage?tier=F3")
    assert r_f3.status_code == 200
    assert r_f3.json()["macro_risk"] is not None

def test_tech_tier_adaptation_and_redaction():
    # T1: Read-only monitor, cannot trigger daemons, cannot override redaction
    r_t1 = client.get("/api/v1/portal/tech/telemetry?tier=T1")
    assert r_t1.status_code == 200
    assert r_t1.json()["can_trigger_daemons"] is False
    assert r_t1.json()["can_override_redaction"] is False
    assert r_t1.json()["redaction_active"] is True

    # T3 with token: unredacted
    r_t3 = client.get("/api/v1/portal/tech/telemetry?tier=T3&unredact_token=AUTH-CA-OVERRIDE-TEMP")
    assert r_t3.status_code == 200
    assert r_t3.json()["redaction_active"] is False

def test_scoped_assistants():
    # Member Tutor
    r_m = client.post("/api/v1/portal/member/ai-tutor", json={"query": "Explain compounding"})
    assert r_m.status_code == 200
    assert "snowball" in r_m.json()["response"]

    # Fiduciary Copilot
    r_f = client.post("/api/v1/portal/advisor/copilot", json={"query": "Explain trade rationale"})
    assert r_f.status_code == 200
    assert "28.5% edge" in r_f.json()["response"]

    # Tech Copilot
    r_t = client.post("/api/v1/portal/tech/copilot", json={"query": "Check rate limits"})
    assert r_t.status_code == 200
    assert "85% capacity" in r_t.json()["response"]
