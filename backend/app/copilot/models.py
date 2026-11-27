"""Transport models shared by Copilot providers and the orchestration layer."""

from typing import Any, Dict, List, Literal, Optional
import uuid

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
    action_id: Optional[str] = None
    action_type: str
    auth_tier: str = "AUTH-01"
    title: str
    description: str = ""
    ui_target: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    destructive: bool = False
    requires_dual_control: bool = False
    requires_settlor_approval: bool = True
    requires_human_confirmation: bool = True
    unilateral_execution: bool = False
    executed: bool = False
    is_disabled: bool = False
    confirmation_notice: str = (
        "Non-executing proposal under AUTH-01–AUTH-04: explicit human confirmation is required."
    )


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
    model_used: Optional[str] = None
    fallback_used: bool = False
    unilateral_execution: bool = False
    auth_tier: str = "AUTH-01"
    guard_blocked: bool = False
    guard_category: Optional[str] = None
    audit_event_id: Optional[str] = None
    policy_decision_matrix: Optional[Dict[str, Any]] = None
    governance_posture: Optional[Dict[str, Any]] = None
    answered_locally: bool = False
    media_refs: List[Dict[str, Any]] = Field(default_factory=list)
    playbook_steps: List[str] = Field(default_factory=list)
    manual_citations: List[Dict[str, Any]] = Field(default_factory=list)
