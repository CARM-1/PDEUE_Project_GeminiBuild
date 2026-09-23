"""REST transport for the role-scoped Stage 2 AI Copilot."""

import os

from fastapi import APIRouter
from pydantic import BaseModel

from app.copilot.engine import AICopilotEngine
from app.copilot.models import CopilotQuery, CopilotResponse


router = APIRouter(prefix="/api/v1/copilot", tags=["Copilot"])


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


# A module-level dependency keeps status and query consistent and permits a
# deployment (or a test) to replace the engine atomically.
copilot_engine = AICopilotEngine(
    emergency_kill_switch=_env_flag("COPILOT_KILL_SWITCH")
)


class CopilotStatus(BaseModel):
    provider_type: str
    model_name: str
    kill_switch_active: bool


@router.post("/query", response_model=CopilotResponse)
async def query_copilot(query: CopilotQuery) -> CopilotResponse:
    """Generate guidance after role projection, R12 redaction, and validation."""
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
