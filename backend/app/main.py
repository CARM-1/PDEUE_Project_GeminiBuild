import os
import pathlib
from urllib.parse import quote
try:
    from app.api.v1.portal_router import portal_router
except ImportError:
    from backend.app.api.v1.portal_router import portal_router
from fastapi.staticfiles import StaticFiles
from app.api.v1.health_router import health_router
from app.api.v1.accounting_router import router as accounting_router
from app.api.v1.copilot_router import router as copilot_router
from app.api.v1.auth_router import auth_router
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from typing import Dict, Any, List
from app.domain.paper_session import PaperSessionManager
from app.domain.decision_packet import DecisionPacketBuilder
from app.domain.authority_tiers import (
    get_governance_audit_log,
    is_chief_admin_deputy_role,
    resolve_deputy_observer_flag,
)
from app.domain.session_auth_service import (
    SESSION_COOKIE_NAME,
    authorize_session_for_request,
    get_session_auth_service,
    is_auth_exempt_path,
    is_html_portal_path,
    is_session_auth_enforced,
)

app = FastAPI(title="PDEUE Operator Workspace API", version="1.0.0")

# Strictly non-mutating educational/advisory Q&A endpoints allowed during Read-Only Deputy Shadow Mode.
_DEPUTY_READ_ONLY_ALLOWED_POST_PATHS = frozenset(
    {
        "/api/v1/copilot/query",
        "/api/v1/operator/chancellor/query",
        "/api/v1/operator/ai-chat",
        "/api/v1/operator/copilot/chat",
        "/operator/copilot/chat",
        "/api/v1/portal/lineage/tutor",
        "/api/v1/auth/logout",
    }
)


@app.middleware("http")
async def enforce_chief_admin_deputy_read_only(request: Request, call_next):
    """Fail-closed HTTP 403 lock on all mutating endpoints when operating as CHIEF_ADMIN_DEPUTY."""
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        auth_session = getattr(request.state, "auth_session", None)
        is_deputy = (
            bool(auth_session and is_chief_admin_deputy_role(auth_session.active_hat))
            or resolve_deputy_observer_flag(
                role=request.query_params.get("role"),
                x_pdeue_role=request.headers.get("X-PDEUE-Role"),
                x_actor_role=request.headers.get("X-Actor-Role"),
                x_active_hat=request.headers.get("X-Active-Hat"),
                authorization=request.headers.get("Authorization"),
            )
        )
        if is_deputy and request.url.path not in _DEPUTY_READ_ONLY_ALLOWED_POST_PATHS:
            actor_id = (
                (auth_session.user_id if auth_session else None)
                or request.headers.get("X-Actor-ID")
                or "CHIEF_ADMIN_DEPUTY"
            )
            get_governance_audit_log().record(
                event_type="DEPUTY_READ_ONLY_MUTATION_BLOCKED",
                actor_id=actor_id,
                actor_role="CHIEF_ADMIN_DEPUTY",
                target_id=request.url.path,
                action=f"{request.method.upper()} {request.url.path}",
                outcome="DENIED_DEPUTY_READ_ONLY_OBSERVER",
                http_status=403,
                detail=(
                    "Blocked mutating request from CHIEF_ADMIN_DEPUTY in Read-Only Shadow "
                    "Succession Mode (DEPUTY_READ_ONLY_OBSERVER)."
                ),
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "DEPUTY_READ_ONLY_OBSERVER: CHIEF_ADMIN_DEPUTY operates in Read-Only "
                        "Shadow Succession Mode. Destructive and mutating actions are locked."
                    ),
                    "error_code": "DEPUTY_READ_ONLY_OBSERVER",
                    "role": "CHIEF_ADMIN_DEPUTY",
                    "read_only": True,
                    "path": request.url.path,
                },
            )
    return await call_next(request)


@app.middleware("http")
async def enforce_session_auth_and_tenant_jail(request: Request, call_next):
    """Fail-closed PR #98 session cookie validation, Active-Hat lock, and server-side tenant jailing."""
    path = request.url.path
    if is_auth_exempt_path(path):
        return await call_next(request)

    cookie_val = request.cookies.get(SESSION_COOKIE_NAME)
    strict_mode = is_session_auth_enforced()

    if cookie_val:
        ctx, err = get_session_auth_service().validate_session_cookie(cookie_val, touch=True)
        if ctx is None:
            get_governance_audit_log().record(
                event_type="AUTH_SESSION_REJECTED",
                actor_id="session_cookie",
                actor_role="UNAUTHENTICATED",
                target_id=path,
                action=f"{request.method.upper()} {path}",
                outcome=f"DENIED_{err or 'INVALID_SESSION'}",
                http_status=401,
                detail=f"Rejected invalid, expired, idle-timed-out, or revoked session cookie ({err}).",
            )
            if is_html_portal_path(path):
                resp = RedirectResponse(url="/login?reason=session_expired", status_code=302)
            else:
                resp = JSONResponse(
                    status_code=401,
                    content={
                        "detail": "Session expired, revoked, or invalid. Please sign in again.",
                        "error_code": err or "SESSION_INVALID",
                    },
                )
            resp.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
            return resp

        request.state.auth_session = ctx
        allowed, err_code, detail = authorize_session_for_request(
            ctx,
            path=path,
            query_params=dict(request.query_params),
            method=request.method,
        )
        if not allowed:
            get_governance_audit_log().record(
                event_type="TENANT_JAIL_VIOLATION" if err_code == "TENANT_JAIL_VIOLATION" else "ACTIVE_HAT_DENIED",
                actor_id=ctx.user_id,
                actor_role=ctx.active_hat,
                target_id=path,
                action=f"{request.method.upper()} {path}",
                outcome=f"DENIED_{err_code}",
                http_status=403,
                detail=detail,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": detail,
                    "error_code": err_code,
                    "active_hat": ctx.active_hat,
                    "path": path,
                },
            )
        return await call_next(request)

    if strict_mode:
        get_governance_audit_log().record(
            event_type="AUTH_UNAUTHENTICATED_BLOCKED",
            actor_id="anonymous",
            actor_role="UNAUTHENTICATED",
            target_id=path,
            action=f"{request.method.upper()} {path}",
            outcome="DENIED_AUTH_REQUIRED",
            http_status=401,
            detail="Blocked unauthenticated request while PDEUE_ENFORCE_SESSION_AUTH=true.",
        )
        if is_html_portal_path(path):
            next_param = quote(path, safe="/")
            return RedirectResponse(url=f"/login?next={next_param}", status_code=302)
        return JSONResponse(
            status_code=401,
            content={
                "detail": "Authentication required. Please sign in at /login.",
                "error_code": "AUTH_REQUIRED",
            },
        )

    return await call_next(request)


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
app.include_router(auth_router)


# Mount air-gapped social/heritage/comms router, shadow hunch router, portal router, and static assets
from app.api.v1.social_plane_router import social_plane_router
from app.api.v1.hunch_router import hunch_router
app.include_router(social_plane_router)
app.include_router(hunch_router)
app.include_router(portal_router)
static_path = pathlib.Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=str(static_path)), name='static')
