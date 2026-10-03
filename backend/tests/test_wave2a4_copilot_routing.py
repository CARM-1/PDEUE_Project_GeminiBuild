"""Wave 2A.4 advisor endpoint integration contracts."""
from fastapi.testclient import TestClient

from app.main import app


CLIENT = TestClient(app)


def _ask(question: str) -> dict:
    response = CLIENT.post(
        "/api/v1/portal/advisor/copilot",
        json={"question": question, "context_scope": "F2_ADVISOR"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "FIDUCIARY_COPILOT"
    assert payload["disclaimer"] == "EDUCATIONAL_NOT_ADVICE"
    return payload


def test_advisor_copilot_endpoint_returns_waterfall_explanation():
    text = _ask("Explain the 87/10/3 waterfall simply")["response_text"]
    assert all(term in text for term in ("87%", "Familial Common Treasury", "FSAP", "Stewardship"))
    assert "never from member pockets" in text


def test_advisor_copilot_endpoint_returns_quarter_kelly_explanation():
    text = _ask("Why do we use quarter-Kelly sizing?")["response_text"]
    assert "one quarter" in text
    assert "chance of ruin" in text
    assert "compounding" in text


def test_advisor_copilot_preserves_withdrawal_impact_rationale():
    text = _ask("Explain the withdrawal impact for Julian")["response_text"]
    assert "24.2%" in text
    assert "$250.00" in text
    assert "compounding" in text
