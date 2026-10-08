"""Contract tests for the zero-CDN member visualization desktop."""
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_member_desktop_contains_native_svg_visualizations():
    response = client.get("/member")
    assert response.status_code == 200
    html = response.text

    assert 'id="asset-rings-view"' in html
    assert "<svg" in html
    assert "<circle" in html
    assert 'stroke-dasharray="' in html
    assert 'id="trajectory-view"' in html
    assert "<path" in html
    assert 'fill="url(#trajectory-fill)"' in html
    assert 'stroke="#38bdf8"' in html
    assert 'id="radar-view"' in html
    assert "wf87" in html and "wf10" in html and "wf3" in html
    assert "87% SCMA" in html and "10% Family Shield" in html and "3% Platform Ops" in html


def test_member_desktop_remains_air_gapped_and_preserves_legacy_anchors():
    html = client.get("/member").text
    lowered = html.lower()
    assert "unpkg" not in lowered
    assert "cdnjs" not in lowered
    assert "chart.js" not in lowered
    assert '<script src="http' not in lowered
    for marker in (
        "My Trajectory",
        "Asset Engine Rings",
        "High-Yield Radar",
        '<div style="display:none" id="legacyPortalHub">PDEUE PORTAL HUB</div>',
        "Downward-Only Risk Governor",
        "AI Tutor drawer",
    ):
        assert marker in html


def test_member_visualization_state_uses_integer_cents_and_basis_points():
    response = client.get("/api/v1/portal/member/state")
    assert response.status_code == 200
    state = response.json()

    allocation = state["allocation"]
    for field in ("cap_cents", "active_float_cents", "active_utilization_bps", "reserve_floor_cents", "reserve_floor_bps", "swept_reserve_cents", "earned_yield_cents", "apy_bps"):
        assert isinstance(allocation[field], int)
    assert allocation["reserve_floor_bps"] == 4000
    assert allocation["apy_bps"] == 450

    assert [point["milestone"] for point in state["trajectory_points"]] == [
        "Seed Capital", "First Settlement", "40% Shield", "High-Watermark Sweep"
    ]
    assert all(isinstance(point["balance_cents"], int) for point in state["trajectory_points"])
    assert all(isinstance(point["yield_increment_cents"], int) for point in state["trajectory_points"])
    assert state["recent_settled_contracts"]
    cent_fields = ("gross_win_cents", "scma_cents", "family_shield_cents", "platform_ops_cents")
    assert all(isinstance(contract[field], int) for contract in state["recent_settled_contracts"] for field in cent_fields)
