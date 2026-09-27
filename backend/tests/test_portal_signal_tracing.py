"""Four-angle signal tracing for every registered PDEUE portal."""
from pathlib import Path
import re

from fastapi.testclient import TestClient

from app.main import app
from app.portal_discovery import PORTALS, generate_inventory
from app.api.v1 import portal_router

ROOT = Path(__file__).resolve().parents[2]
CLIENT = TestClient(app)


def _sources():
    return [(route, (ROOT / "backend" / relative).read_text(encoding="utf-8")) for route, relative in PORTALS.items()]


def test_dynamic_component_catalog_is_current():
    """The committed artifact is reproducible, and all four portals are cataloged."""
    generated = generate_inventory(ROOT)
    assert generated == (ROOT / "docs" / "PORTAL_COMPONENT_INVENTORY.md").read_text(encoding="utf-8")
    assert all(route in generated for route in PORTALS)
    assert "[STUB]" not in generated


def test_angle_1_no_dead_buttons_or_alert_handlers():
    for route, source in _sources():
        inline_handlers = re.findall(r"onclick\s*=\s*(['\"])(.*?)\1", source, re.I | re.S)
        assert all("alert(" not in handler for _, handler in inline_handlers), route
        assert not re.search(r"onclick\s*=\s*(['\"])\s*\1", source), route
        buttons = re.findall(r"<button\b[^>]*>(.*?)</button>", source, re.I | re.S)
        assert buttons, f"{route} has no discoverable controls"
        assert all(re.sub(r"<[^>]+>", "", button).strip() for button in buttons)


def test_angle_2_fetch_contracts_are_registered():
    registered = set(app.openapi()["paths"])
    for route, source in _sources():
        for target in re.findall(r"fetch\(['\"]([^'\"?`]+)", source):
            # Normalize the member account template URL before route comparison.
            normalized = re.sub(r"\$\{[^}]+\}", "{scma_id}", target)
            assert normalized in registered, f"{route} fetches unregistered {target}"


def test_angle_3_daemon_and_distribution_mutate_live_state():
    before = CLIENT.get("/api/v1/portal/tech/telemetry?tier=T3").json()["cycle_count"]
    cycle = CLIENT.post("/api/v1/portal/tech/trigger-daemon")
    assert cycle.status_code == 200
    assert cycle.json()["cycle_count"] == before + 1

    portal_router._DISTRIBUTION_STATE["DIST-104"].update(status="PENDING", signature=None)
    signed = CLIENT.post("/api/v1/portal/advisor/co-sign", json={"request_id": "DIST-104", "actor_role": "F2-H"})
    assert signed.status_code == 200
    assert signed.json()["status"] == "CO-SIGNED / STAGED (DUAL-CONTROL RATIFIED)"
    assert portal_router._DISTRIBUTION_STATE["DIST-104"]["signature"]["actor_role"] == "F2-H"


def test_angle_4_override_and_dual_control_fail_closed():
    denied = CLIENT.post("/api/v1/portal/tech/ca-override", json={"token": "wrong"})
    assert denied.status_code == 401
    assert "masking remains active" in denied.json()["detail"]
    masked = CLIENT.get("/api/v1/portal/tech/telemetry?tier=T3").json()
    assert masked["redaction_active"] is True
    assert masked["active_order_ladder"][0]["scma_id"] == "SCMA-MEM-****"
    assert masked["active_order_ladder"][0]["exposure_cents"] == "$****.**"

    for role in ("F1", "F3", "TECHNICAL_OPERATOR"):
        response = CLIENT.post("/api/v1/portal/advisor/co-sign", json={"request_id": "DIST-104", "actor_role": role})
        assert response.status_code == 403


def test_legacy_hub_marker_survives_every_portal_surface():
    for route in PORTALS:
        response = CLIENT.get(route)
        assert response.status_code == 200
        assert '<div style="display:none" id="legacyPortalHub">PDEUE PORTAL HUB</div>' in response.text
