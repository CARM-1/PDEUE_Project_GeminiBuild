import asyncio

import pytest

from app.copilot.context import ContextHarvester
from app.copilot.engine import AICopilotEngine
from app.copilot.models import CopilotQuery
from app.copilot.providers import MockHeuristicProvider


def test_mock_provider_returns_structured_deterministic_guidance():
    provider = MockHeuristicProvider()
    query = CopilotQuery(prompt="How is my risk?", user_id="member-1", role="MEMBER")
    context = {"current_risk_pct": 2.5, "dry_powder_cents": 125_00, "downward_only_locked": True}

    first = asyncio.run(provider.generate_response(query, context))
    second = asyncio.run(provider.generate_response(query, context))

    assert first == second
    assert first.provider_used == "mock"
    assert first.risk_telemetry.current_risk_pct == 2.5
    assert first.action_cards[0].requires_settlor_approval is True


def test_context_is_isolated_by_role_and_sensitive_values_are_redacted():
    live = {
        "scma_balance_cents": 50_000,
        "current_risk_pct": 1.5,
        "downward_only_locked": True,
        "household_tree": [{"scma_id": "SCMA-ABCD1234", "api_token": "raw-token"}],
        "audit_log_queue": [],
        "sub_account_summaries": [],
        "orderbook_state": {"secret": "do-not-leak"},
    }
    harvester = ContextHarvester()

    member = harvester.harvest(CopilotQuery(prompt="status", user_id="m", role="MEMBER"), live)
    advisor = harvester.harvest(CopilotQuery(prompt="status", user_id="a", role="ADVISOR"), live)

    assert "household_tree" not in member
    assert "current_risk_pct" not in advisor
    assert advisor["household_tree"][0]["scma_id"] == "SCMA-[REDACTED]"
    assert advisor["household_tree"][0]["api_token"] == "[REDACTED]"


def test_emergency_stop_fails_closed_without_invoking_provider():
    class ExplodingProvider(MockHeuristicProvider):
        async def generate_response(self, query, harvested_context):
            raise AssertionError("provider must not run")

    engine = AICopilotEngine(provider=ExplodingProvider(), emergency_kill_switch=True)
    response = asyncio.run(engine.generate_response(
        CopilotQuery(prompt="place an order", user_id="operator-1", role="OPERATOR")
    ))

    assert response.provider_used == "kill-switch"
    assert response.action_cards[0].is_disabled is True
    assert response.risk_telemetry.downward_only_locked is True


@pytest.mark.parametrize("provider_name, key", [("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")])
def test_missing_api_key_selects_mock_provider(monkeypatch, provider_name, key):
    monkeypatch.delenv(key, raising=False)
    engine = AICopilotEngine(provider=provider_name)

    response = asyncio.run(engine.generate_response(
        CopilotQuery(prompt="status", user_id="operator-1", role="TECH")
    ))

    assert isinstance(engine.provider, MockHeuristicProvider)
    assert response.provider_used == "mock"
