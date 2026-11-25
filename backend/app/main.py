import os
import pathlib
try:
    from app.api.v1.portal_router import portal_router
except ImportError:
    from backend.app.api.v1.portal_router import portal_router
from fastapi.staticfiles import StaticFiles
from app.api.v1.health_router import health_router
from app.api.v1.accounting_router import router as accounting_router
from app.api.v1.copilot_router import router as copilot_router
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Dict, Any, List
from app.domain.paper_session import PaperSessionManager
from app.domain.decision_packet import DecisionPacketBuilder

app = FastAPI(title="PDEUE Operator Workspace API", version="1.0.0")


@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirect bare root URL directly to the Central Family Home Hub."""
    return RedirectResponse(url="/home", status_code=302)
paper_manager = PaperSessionManager()
packet_builder = DecisionPacketBuilder()

class CreateSessionRequest(BaseModel):
    initial_capital_cents: int

class PaperTradeRequest(BaseModel):
    session_id: str
    contract_id: str
    price: float
    quantity: int


def _paper_mode_health_metadata() -> Dict[str, Any]:
    """Return fail-closed paper/observation runtime metadata for health probes."""
    venue_mode = os.getenv("PDEUE_VENUE_MODE", "paper").strip().lower() or "paper"
    live_trading_enabled = os.getenv("PDEUE_LIVE_TRADING_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    governance_mode = (
        os.getenv("PDEUE_GOVERNANCE_MODE", "EXECUTIVE_COMMAND").strip().upper()
        or "EXECUTIVE_COMMAND"
    )
    gate_g1_status = (
        os.getenv("PDEUE_GATE_G1_STATUS", "HOLD_OBSERVATIONS_ONLY").strip().upper()
        or "HOLD_OBSERVATIONS_ONLY"
    )
    return {
        "venue_mode": venue_mode,
        "paper_mode": venue_mode in {"paper", "observation"} and not live_trading_enabled,
        "live_trading_enabled": live_trading_enabled,
        "governance_mode": governance_mode,
        "gate_g1_status": gate_g1_status,
        "synthetic_fills_present": False,
    }


@app.get("/health")
def health_check():
    return {"status": "HEALTHY", "healthy": True, **_paper_mode_health_metadata()}

@app.get("/healthz")
def readiness_check():
    """Lightweight, dependency-free health probe for orchestrators."""
    return {
        "status": "HEALTHY",
        "healthy": True,
        "circuit_breaker_tripped": False,
        **_paper_mode_health_metadata(),
    }

@app.post("/api/v1/paper/sessions")
def create_paper_session(req: CreateSessionRequest):
    return paper_manager.create_session(req.initial_capital_cents)

@app.post("/api/v1/paper/trade")
def execute_trade(req: PaperTradeRequest):
    try:
        return paper_manager.execute_paper_trade(req.session_id, req.contract_id, req.price, req.quantity)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

try:
    from app.api.v1.operator_router import router as operator_router
    app.include_router(operator_router, prefix="/api/v1")
except Exception:
    pass

from app.api.v1.workspace_router import workspace_router
from app.api.v1.lineage_router import lineage_router
from app.api.v1.onboarding_router import onboarding_router
app.include_router(workspace_router)
app.include_router(lineage_router)
app.include_router(onboarding_router)

app.include_router(accounting_router)
app.include_router(copilot_router)


app.include_router(health_router)


# Mount air-gapped social/heritage/comms router, shadow hunch router, portal router, and static assets
from app.api.v1.social_plane_router import social_plane_router
from app.api.v1.hunch_router import hunch_router
app.include_router(social_plane_router)
app.include_router(hunch_router)
app.include_router(portal_router)
static_path = pathlib.Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=str(static_path)), name='static')
