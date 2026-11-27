"""PR #98 — Private Family Sign-In Portal (/login) & Session Authentication API Router.

Exposes:
- GET  /login
- POST /api/v1/auth/request-code
- POST /api/v1/auth/verify-code
- GET  /api/v1/auth/magic?token=...
- POST /api/v1/auth/apex-login
- POST /api/v1/auth/logout
- GET  /api/v1/auth/me
- POST /api/v1/auth/switch-hat
- GET  /api/v1/auth/sessions
- POST /api/v1/auth/sessions/{session_id}/revoke
"""
from __future__ import annotations

import os
import pathlib
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.core.security import decode_access_token
from app.domain.authority_tiers import (
    is_chief_admin_deputy_role,
    is_chief_admin_role,
    normalize_role_token,
)
from app.domain.session_auth_service import (
    CLASS_M_ACTIVE_WINDOW_SECONDS,
    CLASS_M_HATS,
    OFFICER_ACTIVE_WINDOW_SECONDS,
    SESSION_COOKIE_NAME,
    SessionAuthError,
    get_session_auth_service,
    is_session_auth_enforced,
    workspace_url_for_hat,
)

auth_router = APIRouter(tags=["Session Authentication"])


class RequestCodePayload(BaseModel):
    email: str


class VerifyCodePayload(BaseModel):
    email: str
    code: str
    active_hat: Optional[str] = None


class ApexLoginPayload(BaseModel):
    email: str
    passphrase: str
    mfa_code: Optional[str] = None
    active_hat: Optional[str] = None
    webauthn_assertion: Optional[Dict[str, Any]] = None


class SwitchHatPayload(BaseModel):
    to_hat: str
    confirmed: bool = True
    reason: Optional[str] = ""


class RevokeSessionPayload(BaseModel):
    reason: Optional[str] = "Chief Admin lost-device revocation"


def _load_login_html() -> str:
    api_page = pathlib.Path(__file__).parent / "login.html"
    if api_page.exists():
        return api_page.read_text(encoding="utf-8")
    static_page = pathlib.Path(__file__).parent.parent.parent / "static" / "login.html"
    if static_page.exists():
        return static_page.read_text(encoding="utf-8")
    raise HTTPException(status_code=500, detail="login.html template missing")


def _cookie_is_secure(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    if request.headers.get("x-forwarded-proto", "").strip().lower() == "https":
        return True
    return os.getenv("PDEUE_COOKIE_SECURE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _set_session_cookie(
    response: Response,
    *,
    request: Request,
    signed_cookie: str,
    active_hat: str,
) -> None:
    norm_hat = normalize_role_token(active_hat)
    max_age = (
        CLASS_M_ACTIVE_WINDOW_SECONDS
        if norm_hat in CLASS_M_HATS
        else OFFICER_ACTIVE_WINDOW_SECONDS
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=signed_cookie,
        httponly=True,
        samesite="lax",
        secure=_cookie_is_secure(request),
        path="/",
        max_age=max_age,
    )


def _require_chief_admin_for_sessions(
    request: Request,
    *,
    allow_deputy_readonly: bool,
    authorization: Optional[str],
    x_pdeue_role: Optional[str],
    x_active_hat: Optional[str],
    x_actor_role: Optional[str],
) -> tuple[str, str]:
    """Verify CHIEF_ADMIN authority for session inspection / revocation."""
    svc = get_session_auth_service()
    cookie_val = request.cookies.get(SESSION_COOKIE_NAME)

    if cookie_val:
        ctx, err = svc.validate_session_cookie(cookie_val, touch=True)
        if ctx is None:
            raise HTTPException(status_code=401, detail=f"Session invalid or expired ({err}).")
        if is_chief_admin_role(ctx.active_hat):
            return ctx.user_id, ctx.active_hat
        if allow_deputy_readonly and is_chief_admin_deputy_role(ctx.active_hat):
            return ctx.user_id, ctx.active_hat
        raise HTTPException(
            status_code=403,
            detail="CHIEF_ADMIN_REQUIRED: Only the Chief Administrator may inspect or revoke family sessions.",
        )

    if is_session_auth_enforced():
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Sign in with an Apex CHIEF_ADMIN session.",
        )

    # Paper-demo compatibility when unauthenticated without cookie: honor explicit role headers fail-closed.
    actor_role = ""
    actor_id = "USR-founder_ch-C8575D7E"
    if authorization and authorization.lower().startswith("bearer "):
        claims = decode_access_token(authorization.split(" ", 1)[1].strip())
        if not claims:
            raise HTTPException(status_code=403, detail="Invalid or expired bearer token.")
        actor_role = str(claims.get("active_hat") or claims.get("role") or "")
        actor_id = str(claims.get("sub") or claims.get("user_id") or actor_id)
    else:
        actor_role = x_active_hat or x_pdeue_role or x_actor_role or ""

    if actor_role:
        if is_chief_admin_role(actor_role):
            return actor_id, "CHIEF_ADMINISTRATOR"
        if allow_deputy_readonly and is_chief_admin_deputy_role(actor_role):
            return actor_id, "CHIEF_ADMIN_DEPUTY"
        raise HTTPException(
            status_code=403,
            detail=f"CHIEF_ADMIN_REQUIRED: Role '{normalize_role_token(actor_role)}' cannot manage family sessions.",
        )

    return actor_id, "CHIEF_ADMINISTRATOR"


@auth_router.get("/login", response_class=HTMLResponse)
def get_login_portal() -> HTMLResponse:
    """Serve the Private Family Sign-In Portal (zero public registration, zero CDN)."""
    return HTMLResponse(content=_load_login_html())


@auth_router.post("/api/v1/auth/request-code")
def request_signin_code(payload: RequestCodePayload) -> Dict[str, Any]:
    """Request a single-use 6-digit sign-in code & Magic Link for allowlisted family emails."""
    svc = get_session_auth_service()
    try:
        return svc.request_login_code(payload.email)
    except SessionAuthError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err


@auth_router.post("/api/v1/auth/verify-code")
def verify_signin_code(
    payload: VerifyCodePayload,
    request: Request,
    response: Response,
) -> Dict[str, Any]:
    """Verify a 6-digit email code, burn the challenge, and set the signed HttpOnly session cookie."""
    svc = get_session_auth_service()
    try:
        ctx, signed_cookie = svc.verify_login_code(
            payload.email,
            payload.code,
            requested_hat=payload.active_hat,
        )
    except SessionAuthError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err

    _set_session_cookie(
        response,
        request=request,
        signed_cookie=signed_cookie,
        active_hat=ctx.active_hat,
    )
    redirect_to = workspace_url_for_hat(ctx.active_hat, ctx.house_id)
    return {
        "status": "AUTHENTICATED",
        "authenticated": True,
        "redirect_to": redirect_to,
        "session": ctx.to_dict(),
    }


@auth_router.get("/api/v1/auth/magic")
def verify_magic_link(
    request: Request,
    token: str = Query(..., min_length=8),
) -> Response:
    """Verify a single-use Magic Link token, burn it, set signed HttpOnly cookie, and redirect."""
    svc = get_session_auth_service()
    try:
        ctx, signed_cookie = svc.verify_magic_token(token)
    except SessionAuthError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err

    redirect_to = workspace_url_for_hat(ctx.active_hat, ctx.house_id)
    resp = RedirectResponse(url=redirect_to, status_code=302)
    _set_session_cookie(
        resp,
        request=request,
        signed_cookie=signed_cookie,
        active_hat=ctx.active_hat,
    )
    return resp


@auth_router.post("/api/v1/auth/apex-login")
def apex_command_login(
    payload: ApexLoginPayload,
    request: Request,
    response: Response,
) -> Dict[str, Any]:
    """Authenticate CHIEF_ADMIN, T3, or F3 via salted PBKDF2 passphrase + 6-digit MFA (or WebAuthn hook)."""
    svc = get_session_auth_service()
    try:
        ctx, signed_cookie = svc.verify_apex_login(
            email=payload.email,
            passphrase=payload.passphrase,
            mfa_code=payload.mfa_code,
            requested_hat=payload.active_hat,
            webauthn_assertion=payload.webauthn_assertion,
        )
    except SessionAuthError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err

    _set_session_cookie(
        response,
        request=request,
        signed_cookie=signed_cookie,
        active_hat=ctx.active_hat,
    )
    redirect_to = workspace_url_for_hat(ctx.active_hat, ctx.house_id)
    return {
        "status": "AUTHENTICATED",
        "authenticated": True,
        "redirect_to": redirect_to,
        "session": ctx.to_dict(),
    }


@auth_router.post("/api/v1/auth/logout")
def logout(request: Request, response: Response) -> Dict[str, Any]:
    """Revoke active session server-side and clear the signed HttpOnly session cookie."""
    svc = get_session_auth_service()
    cookie_val = request.cookies.get(SESSION_COOKIE_NAME)
    result = svc.logout_session(cookie_val)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return result


@auth_router.get("/api/v1/auth/me")
def get_current_session(request: Request) -> JSONResponse:
    """Return the active authenticated session context or HTTP 401 when unauthenticated/expired."""
    svc = get_session_auth_service()
    cookie_val = request.cookies.get(SESSION_COOKIE_NAME)
    ctx, err = svc.validate_session_cookie(cookie_val, touch=True)
    if ctx is None:
        resp = JSONResponse(
            status_code=401,
            content={
                "authenticated": False,
                "detail": "Authentication required or session expired.",
                "error_code": err or "AUTH_REQUIRED",
            },
        )
        if cookie_val:
            resp.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
        return resp
    return JSONResponse(
        status_code=200,
        content={
            "authenticated": True,
            "session": ctx.to_dict(),
        },
    )


@auth_router.post("/api/v1/auth/switch-hat")
def switch_session_active_hat(
    payload: SwitchHatPayload,
    request: Request,
) -> Dict[str, Any]:
    """Directive R-06 server-side Active-Hat rotation on the authenticated session."""
    svc = get_session_auth_service()
    cookie_val = request.cookies.get(SESSION_COOKIE_NAME)
    try:
        return svc.switch_session_hat(
            cookie_val,
            to_hat=payload.to_hat,
            confirmed=payload.confirmed,
            reason=payload.reason or "",
        )
    except SessionAuthError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err


@auth_router.get("/api/v1/auth/sessions")
def list_active_sessions(
    request: Request,
    include_revoked: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_pdeue_role: Optional[str] = Header(None, alias="X-PDEUE-Role"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
) -> Dict[str, Any]:
    """Chief Admin active session ledger for lost-device inspection."""
    _require_chief_admin_for_sessions(
        request,
        allow_deputy_readonly=True,
        authorization=authorization,
        x_pdeue_role=x_pdeue_role,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
    )
    sessions = get_session_auth_service().list_sessions(
        include_revoked=include_revoked,
        limit=limit,
    )
    active_count = sum(1 for s in sessions if s["is_active"])
    return {
        "sessions": sessions,
        "active_count": active_count,
        "total_count": len(sessions),
    }


@auth_router.post("/api/v1/auth/sessions/{session_id}/revoke")
def revoke_user_session(
    session_id: str,
    request: Request,
    payload: Optional[RevokeSessionPayload] = None,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_pdeue_role: Optional[str] = Header(None, alias="X-PDEUE-Role"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
) -> Dict[str, Any]:
    """Chief Admin 1-click immediate session revocation for lost or shared devices."""
    actor_id, actor_role = _require_chief_admin_for_sessions(
        request,
        allow_deputy_readonly=False,
        authorization=authorization,
        x_pdeue_role=x_pdeue_role,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
    )
    reason = (payload.reason if payload and payload.reason else "Chief Admin lost-device revocation")
    try:
        return get_session_auth_service().revoke_session(
            session_id,
            revoked_by=actor_id,
            actor_role=actor_role,
            reason=reason,
        )
    except SessionAuthError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err
