"""Transport models shared by Copilot providers and the orchestration layer."""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class CopilotQuery(BaseModel):
    prompt: str = Field(min_length=1)
    user_id: str
    role: str
    context_filters: Dict[str, Any] = Field(default_factory=dict)


class ActionCard(BaseModel):
    action_type: str
    title: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    requires_settlor_approval: bool = True
    is_disabled: bool = False


class RiskTelemetry(BaseModel):
    current_risk_pct: float = 0.0
    dry_powder_cents: int = 0
    downward_only_locked: bool = True


class CopilotResponse(BaseModel):
    answer_text: str
    citations: List[str] = Field(default_factory=list)
    action_cards: List[ActionCard] = Field(default_factory=list)
    risk_telemetry: RiskTelemetry = Field(default_factory=RiskTelemetry)
    provider_used: str
