"""Pluggable, role-aware AI Copilot engine."""

from .engine import AICopilotEngine
from .models import ActionCard, CopilotQuery, CopilotResponse, RiskTelemetry
from .providers import AnthropicProvider, BaseProvider, MockHeuristicProvider, OpenAIProvider

__all__ = [
    "AICopilotEngine",
    "ActionCard",
    "AnthropicProvider",
    "BaseProvider",
    "CopilotQuery",
    "CopilotResponse",
    "MockHeuristicProvider",
    "OpenAIProvider",
    "RiskTelemetry",
]
