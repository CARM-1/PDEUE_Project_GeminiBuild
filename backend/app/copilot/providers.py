"""Provider implementations for the Copilot engine.

The hosted adapters deliberately accept an injected client.  This keeps the core
free of vendor SDK dependencies and makes provider behavior straightforward to
test.  No credential ever means no outbound request: the deterministic provider
is used instead.
"""

from abc import ABC, abstractmethod
import inspect
import os
from typing import Any, Mapping, Optional

from .models import ActionCard, CopilotQuery, CopilotResponse, RiskTelemetry


def _risk(context: Mapping[str, Any]) -> RiskTelemetry:
    source = context.get("risk_telemetry", context)
    return RiskTelemetry(
        current_risk_pct=float(source.get("current_risk_pct", 0.0)),
        dry_powder_cents=int(source.get("dry_powder_cents", 0)),
        downward_only_locked=bool(source.get("downward_only_locked", True)),
    )


class BaseProvider(ABC):
    """Interface implemented by every Copilot completion provider."""

    name = "base"

    @abstractmethod
    async def generate_response(
        self, query: CopilotQuery, harvested_context: Mapping[str, Any]
    ) -> CopilotResponse:
        raise NotImplementedError


class MockHeuristicProvider(BaseProvider):
    """Deterministic local guidance, suitable for tests and failover."""

    name = "mock"

    async def generate_response(self, query, harvested_context) -> CopilotResponse:
        role = query.role.upper()
        telemetry = _risk(harvested_context)
        if role == "MEMBER":
            answer = (
                f"Member guidance: current risk is {telemetry.current_risk_pct:.2f}%; "
                f"dry powder is {telemetry.dry_powder_cents} cents. "
                "Any risk change remains subject to the downward-only rule."
            )
            cards = [ActionCard(
                action_type="REQUEST_RISK_REVIEW",
                title="Request a risk review",
                payload={"user_id": query.user_id},
                requires_settlor_approval=True,
                is_disabled=telemetry.downward_only_locked,
            )]
        elif role == "ADVISOR":
            answer = "Advisor guidance: review household allocation, queued audits, and sub-account summaries before proposing an action."
            cards = [ActionCard(
                action_type="REVIEW_HOUSEHOLD",
                title="Review household",
                payload={},
                requires_settlor_approval=True,
                is_disabled=False,
            )]
        else:
            answer = "Operator guidance: inspect the orderbook, active dispatches, and telemetry health before intervening."
            cards = [ActionCard(
                action_type="INSPECT_TELEMETRY",
                title="Inspect operational telemetry",
                payload={},
                requires_settlor_approval=True,
                is_disabled=False,
            )]
        return CopilotResponse(
            answer_text=answer,
            citations=["live-context"],
            action_cards=cards,
            risk_telemetry=telemetry,
            provider_used=self.name,
        )


class _HostedProvider(BaseProvider):
    env_key = ""

    def __init__(self, api_key: Optional[str] = None, client: Any = None, fallback: Optional[BaseProvider] = None):
        self.api_key = api_key or os.getenv(self.env_key)
        self.client = client
        self.fallback = fallback or MockHeuristicProvider()

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.client)

    async def generate_response(self, query, harvested_context) -> CopilotResponse:
        if not self.available:
            return await self.fallback.generate_response(query, harvested_context)
        result = self.client.generate_response(query, harvested_context)
        if inspect.isawaitable(result):
            result = await result
        response = result if isinstance(result, CopilotResponse) else CopilotResponse.model_validate(result)
        return response.model_copy(update={"provider_used": self.name})


class OpenAIProvider(_HostedProvider):
    name = "openai"
    env_key = "OPENAI_API_KEY"


class AnthropicProvider(_HostedProvider):
    name = "anthropic"
    env_key = "ANTHROPIC_API_KEY"
