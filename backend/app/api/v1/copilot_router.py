"""REST transport for the role-scoped Stage 2 AI Copilot."""

import os

from fastapi import APIRouter
from pydantic import BaseModel

from app.copilot.engine import AICopilotEngine
from app.copilot.models import ActionCard, CopilotQuery, CopilotResponse, RiskTelemetry
from app.domain.chancellor_coach import ChiefAdminChancellorCoach


router = APIRouter(prefix="/api/v1/copilot", tags=["Copilot"])


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


# A module-level dependency keeps status and query consistent and permits a
# deployment (or a test) to replace the engine atomically.
copilot_engine = AICopilotEngine(
    emergency_kill_switch=_env_flag("COPILOT_KILL_SWITCH")
)
chancellor_coach = ChiefAdminChancellorCoach()


class CopilotStatus(BaseModel):
    provider_type: str
    model_name: str
    kill_switch_active: bool


@router.post("/query", response_model=CopilotResponse)
async def query_copilot(query: CopilotQuery) -> CopilotResponse:
    """Generate guidance after role projection, R12 redaction, and validation."""
    if query.role.upper() == "OPERATOR" and not copilot_engine._is_tripped():
        live_ctx = query.context_filters.get("live_context") if isinstance(query.context_filters, dict) else None
        result = chancellor_coach.advise(
            query.prompt,
            actor_id=query.user_id,
            live_context=live_ctx if isinstance(live_ctx, dict) else None,
        )
        return CopilotResponse(
            answer_text=result["answer_text"],
            citations=list(result.get("citations") or []),
            action_cards=[ActionCard.model_validate(c) for c in (result.get("action_cards") or [])],
            risk_telemetry=RiskTelemetry.model_validate(result.get("risk_telemetry") or {}),
            provider_used=str(result.get("provider_used") or "mock"),
            model_used=result.get("model_used"),
            fallback_used=bool(result.get("fallback_used", False)),
            unilateral_execution=False,
            auth_tier=str(result.get("auth_tier") or "AUTH-01"),
            guard_blocked=bool(result.get("guard_blocked", False)),
            guard_category=result.get("guard_category"),
            audit_event_id=result.get("audit_event_id"),
            policy_decision_matrix=result.get("policy_decision_matrix"),
            governance_posture=result.get("governance_posture"),
        )
    return await copilot_engine.generate_response(query)


@router.get("/status", response_model=CopilotStatus)
def copilot_status() -> CopilotStatus:
    provider = copilot_engine.provider.name
    model_defaults = {
        "mock": "mock-heuristic-v1",
        "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
    }
    return CopilotStatus(
        provider_type=provider,
        model_name=model_defaults.get(provider, provider),
        kill_switch_active=copilot_engine._is_tripped(),
    )
