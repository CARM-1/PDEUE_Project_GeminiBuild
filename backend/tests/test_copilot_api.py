from fastapi.testclient import TestClient
import pytest

from app.api.v1 import copilot_router
from app.copilot.engine import AICopilotEngine
from app.main import app


client = TestClient(app)


@pytest.mark.parametrize("role", ["MEMBER", "ADVISOR", "OPERATOR"])
def test_query_supports_portal_roles(role):
    response = client.post("/api/v1/copilot/query", json={
        "prompt": "Summarize my current risk posture",
        "user_id": f"{role.lower()}-1",
        "role": role,
        "context_filters": {"live_context": {"dry_powder_cents": 12500}},
    })
    assert response.status_code == 200
    assert {"answer_text", "citations", "action_cards", "risk_telemetry"} <= response.json().keys()
    assert isinstance(response.json()["risk_telemetry"]["dry_powder_cents"], int)


def test_status_reports_provider_model_and_kill_switch():
    response = client.get("/api/v1/copilot/status")
    assert response.status_code == 200
    assert response.json()["provider_type"] in {"mock", "openai", "anthropic"}
    assert response.json()["model_name"]
    assert response.json()["kill_switch_active"] is False


def test_kill_switch_returns_fail_closed_action_card(monkeypatch):
    monkeypatch.setattr(copilot_router, "copilot_engine", AICopilotEngine(emergency_kill_switch=True))
    response = client.post("/api/v1/copilot/query", json={
        "prompt": "Execute this trade", "user_id": "operator-1", "role": "OPERATOR"
    })
    assert response.status_code == 200
    assert response.json()["action_cards"][0]["is_disabled"] is True
    assert response.json()["provider_used"] == "kill-switch"


@pytest.mark.parametrize("payload", [
    {},
    {"prompt": "", "user_id": "member-1", "role": "MEMBER"},
    {"prompt": "hello", "user_id": "member-1", "role": "ADMIN"},
    {"prompt": "hello", "user_id": "member-1", "role": "MEMBER", "context_filters": {"amount_cents": 1.25}},
])
def test_malformed_query_is_rejected(payload):
    assert client.post("/api/v1/copilot/query", json=payload).status_code == 422
