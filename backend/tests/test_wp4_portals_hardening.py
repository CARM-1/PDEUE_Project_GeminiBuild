from pathlib import Path

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_tech_console_applies_r12_redaction():
    response = client.get("/api/v1/portal/tech/telemetry?tier=T3")
    assert response.status_code == 200
    order = response.json()["active_order_ladder"][0]
    assert order["scma_id"] == "SCMA-MEM-****"
    assert order["exposure_cents"] == "$****.**"
    assert "ELEANOR" not in str(order)


def test_advisor_workspace_enforces_household_boundary():
    response = client.get(
        "/api/v1/portal/advisor/household-tree?household_id=HOUSEHOLD-BETA",
        headers={"X-Household-ID": "HOUSEHOLD-ALPHA"},
    )
    assert response.status_code == 403


def test_advisor_workspace_renders_custodial_locks():
    api = client.get("/api/v1/portal/advisor/household-tree").json()
    julian = next(account for account in api["accounts"] if account["is_custodial"])
    assert julian["risk_controls_locked"] is True
    assert julian["risk_increase_requires"] == "F2_CO_SIGN"
    page = client.get("/advisor").text
    assert "CUSTODIAL APPRENTICE" in page
    assert "F2 co-sign required" in page


def test_portal_templates_contain_no_external_cdn_scripts():
    roots = (Path("app/api/v1"), Path("app/static"))
    for root in roots:
        for name in ("tech.html", "advisor.html"):
            text = (root / name).read_text(encoding="utf-8").lower()
            assert "<script src=" not in text
            assert all(host not in text for host in ("unpkg", "cdnjs", "jsdelivr"))
            assert '<div style="display:none" id="legacyportalhub">pdeue portal hub</div>' in text
