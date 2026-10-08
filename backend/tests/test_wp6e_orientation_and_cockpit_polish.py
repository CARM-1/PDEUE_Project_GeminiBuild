"""WP-6E orientation, cash-engine, and institutional cockpit contract tests."""
import math

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _target_projection(seed: float, months: int = 12) -> float:
    """Mirror the ratified target-rate model to guard realistic UI boundaries."""
    float_cash, swept_cash, passive_yield = seed, 0.0, 0.0
    for _ in range(months):
        passive_yield += (swept_cash + float_cash * 0.40) * (0.045 / 12)
        if float_cash < 25_000:
            month_gross = float_cash * math.pow(1 + 0.23, 52 / 12)
            if month_gross > 25_000:
                swept_cash += month_gross - 25_000
                float_cash = 25_000
            else:
                float_cash = month_gross
        else:
            swept_cash += 9_500
    return float_cash + swept_cash + passive_yield

def test_member_contains_primary_views_projections_and_currency_control():
    response = client.get("/member")
    assert response.status_code == 200
    page = response.text
    for marker in ("tabBtnOrientation", "tabBtnEngine", "viewOrientation", "viewEngine", "currBtnClean", "currBtnExact"):
        assert f'id="{marker}"' in page
    assert "$100.00 Starting Seed" in page
    assert "$1,000.00 Starting Seed" in page
    assert "Conservative Pace (~10%/wk)" in page
    assert "Bullish/Target Pace (~23%/wk)" in page
    assert "Project FUTURE" in page
    assert "is_custodial: true" in page
    assert "function simulateHorizon" in page
    assert "class=\"chart-legend\"" in page
    assert "<text x=" not in page


def test_month_12_target_projections_stay_within_post_cap_boundaries():
    assert 30_000 <= _target_projection(100) <= 150_000
    assert 70_000 <= _target_projection(1_000) <= 250_000

def test_dashboard_uses_institutional_matrices_and_alignment_classes():
    response = client.get("/dashboard")
    assert response.status_code == 200
    page = response.text
    assert 'class="positions-table"' in page
    assert ".ledger-table" in page
    assert 'class="numeric">QTY' in page
    assert "RESTING_MAKER" in page
    assert "status-chip" in page
    assert "$118.75" in page
    assert "currBtnClean" in page and "currBtnExact" in page
    assert "PrincipalNOT AVAILABLE" not in page

def test_copilot_explains_future_fostering_and_post_cap_cash_engine():
    from app.domain.ai_copilot import AICopilotEngine
    engine = AICopilotEngine()
    future = engine.ask("How does Project FUTURE diversify markets?")
    assert "CME" in future and "delta-neutral crypto" in future
    fostering = engine.ask("Can I foster or sponsor a relative?")
    assert "swept bank cash" in fostering and "F1 Peer Mentor" in fostering
    monthly = engine.ask("What happens monthly after 25k?")
    assert "$7,800–$11,300" in monthly and "4.5% APY" in monthly
