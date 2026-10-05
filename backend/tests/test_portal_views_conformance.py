"""WP-6D portal markup regression tests."""
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_member_orientation_and_performance_ratio_grid():
    response = client.get("/member")
    assert response.status_code == 200
    page = response.text
    assert "📘 Platform Orientation" in page
    assert "Win / Loss Rate" in page
    assert "74.2% (89W / 31L)" in page
    assert "Profit Factor" in page
    assert "Quarter-Kelly (0.25f*)" in page
    assert "Defensive Ceiling: 5.0%" in page


def test_chief_admin_cockpit_controls_and_native_equity_curve():
    response = client.get("/dashboard")
    assert response.status_code == 200
    page = response.text
    assert "EMERGENCY KILL SWITCH" in page
    assert "MODE: PAPER" in page
    assert '<svg id="chart-equity"' in page
    assert 'linearGradient id="equity-fill"' in page
    assert "400,000¢ floor" in page
    assert "PrincipalNOT AVAILABLE" not in page
    assert '<canvas id="chart-equity"' not in page
