"""Copilot provider selection and fail-closed orchestration."""

import os
from typing import Any, Mapping, Optional, Union

from .context import ContextHarvester
from .models import ActionCard, CopilotQuery, CopilotResponse, RiskTelemetry
from .providers import AnthropicProvider, BaseProvider, MockHeuristicProvider, OpenAIProvider


class AICopilotEngine:
    def __init__(
        self,
        provider: Union[str, BaseProvider, None] = None,
        context_harvester: Optional[ContextHarvester] = None,
        emergency_kill_switch: Any = None,
    ):
        self.provider = self._select_provider(provider or os.getenv("COPILOT_PROVIDER", "mock"))
        self.context_harvester = context_harvester or ContextHarvester()
        self.emergency_kill_switch = emergency_kill_switch

    @staticmethod
    def _select_provider(provider: Union[str, BaseProvider]) -> BaseProvider:
        if isinstance(provider, BaseProvider):
            return provider
        name = str(provider).lower()
        candidate: BaseProvider
        if name == "openai":
            candidate = OpenAIProvider()
        elif name == "anthropic":
            candidate = AnthropicProvider()
        else:
            return MockHeuristicProvider()
        return candidate if candidate.available else MockHeuristicProvider()

    def _is_tripped(self) -> bool:
        switch = self.emergency_kill_switch
        if switch is None:
            return False
        if isinstance(switch, bool):
            return switch
        for attribute in ("is_active", "is_tripped", "tripped"):
            value = getattr(switch, attribute, None)
            if value is not None:
                return bool(value() if callable(value) else value)
        return False

    async def generate_response(
        self, query: CopilotQuery, live_context: Optional[Mapping[str, Any]] = None
    ) -> CopilotResponse:
        if not isinstance(query, CopilotQuery):
            query = CopilotQuery.model_validate(query)
        if self._is_tripped():
            return CopilotResponse(
                answer_text="Copilot execution is unavailable while the global emergency stop is active.",
                citations=[],
                action_cards=[ActionCard(
                    action_type="EMERGENCY_STOP_ACTIVE",
                    title="Execution disabled — emergency stop active",
                    payload={},
                    requires_settlor_approval=True,
                    is_disabled=True,
                )],
                risk_telemetry=RiskTelemetry(downward_only_locked=True),
                provider_used="kill-switch",
            )
        context = self.context_harvester.harvest(query, live_context)
        return await self.provider.generate_response(query, context)

    async def process_query(self, query: CopilotQuery, live_context: Optional[Mapping[str, Any]] = None) -> CopilotResponse:
        """Alias retained for application services that use process-oriented naming."""
        return await self.generate_response(query, live_context)
