"""Transport models shared by Copilot providers and the orchestration layer."""

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, field_validator


class CopilotQuery(BaseModel):
    prompt: str = Field(min_length=1, max_length=8_000)
    user_id: str = Field(min_length=1, max_length=256)
    role: Literal["MEMBER", "ADVISOR", "OPERATOR", "TECH"]
    context_filters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt", "user_id")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("context_filters")
    @classmethod
    def enforce_integer_cents(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        """ADR-008: currency crossing the API boundary is integer cents."""
        def check(item: Any, key: str = "context_filters") -> None:
            if key.lower().endswith("_cents") and (isinstance(item, bool) or not isinstance(item, int)):
                raise ValueError(f"{key} must be an integer number of cents")
            if isinstance(item, dict):
                for nested_key, nested_value in item.items():
                    check(nested_value, str(nested_key))
            elif isinstance(item, (list, tuple)):
                for nested_value in item:
                    check(nested_value, key)

        check(value)
        return value


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
