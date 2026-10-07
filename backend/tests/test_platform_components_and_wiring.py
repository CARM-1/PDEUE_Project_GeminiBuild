"""WP-6F regression coverage for portal controls and primary API wires."""

from fastapi.testclient import TestClient

from app.main import app
from scripts.audit_and_test_pdeue import PORTAL_ROUTES, run_audit


def test_member_active_hat_navigation_is_role_siloed():
    with TestClient(app) as client:
        response = client.get("/member")

    assert response.status_code == 200
    nav = response.text.split("</nav>", 1)[0]
    assert "Active Hat: MEMBER_USER" in nav
    assert 'href="/companion"' in nav
    assert 'href="/dashboard"' not in response.text


def test_all_registered_portals_render_without_template_errors():
    with TestClient(app) as client:
        responses = {route: client.get(route) for route in PORTAL_ROUTES}

    assert {route: response.status_code for route, response in responses.items()} == {
        route: 200 for route in PORTAL_ROUTES
    }


def test_component_audit_has_no_dead_controls_and_api_wires_are_green():
    with TestClient(app) as client:
        controls, api_rows = run_audit(client)

    broken_controls = [row for row in controls if row["status"] == "FAIL"]
    failed_wires = [row for row in api_rows if row["verdict"] != "PASS"]
    assert broken_controls == []
    assert failed_wires == []
    assert all(row["status"] in {"200", "201"} for row in api_rows)
