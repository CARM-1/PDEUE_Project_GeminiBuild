"""Acceptance coverage for Tab 2 accordion state across dashboard polling."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _dashboard_html() -> str:
    response = client.get("/dashboard")
    assert response.status_code == 200
    return response.text


def test_dashboard_snapshots_open_house_panels_before_poll_render() -> None:
    html = _dashboard_html()

    assert "const existingNodes = [...tree.querySelectorAll('.house-node')];" in html
    assert "const openHouseIds = new Set(existingNodes" in html
    assert ".filter(node => !node.querySelector('.subaccount-panel').hidden)" in html
    assert ".map(node => String(node.dataset.houseId))" in html
    assert "const isInitialRender = existingNodes.length === 0;" in html


def test_dashboard_restores_panel_accessibility_and_caret_state() -> None:
    html = _dashboard_html()
    preserved_or_initial = (
        "openHouseIds.has(String(house.house_id)) || "
        "(isInitialRender && index === 0)"
    )

    assert f'aria-expanded="${{{preserved_or_initial}}}"' in html
    assert f"${{{preserved_or_initial} ? '▾' : '▸'}}" in html
    assert (
        f'class="subaccount-panel" ${{{preserved_or_initial} ? \'\' : \'hidden\'}}'
        in html
    )


def test_dashboard_keeps_tab_two_controls_and_dynamic_status() -> None:
    html = _dashboard_html()

    for expected in (
        'data-house-id="${house.house_id}"',
        'data-scma="${member.scma_id}"',
        "house-status ${house.status.toLowerCase()}",
        "⚡ Freeze Entire House",
        "↺ Restore House",
        "⚡ Freeze Risk",
        "↺ Restore Risk",
        "✕ Revoke Orders",
    ):
        assert expected in html
