"""Shadow Paper Hunch Research Studio & Clearance Queue API Router (Batch 2B — Part 3).

Registers:
- POST /api/v1/hunch/evaluate
- POST /api/v1/hunch/{dossier_id}/shadow-bid
- POST /api/v1/hunch/{dossier_id}/request-live-clearance
- POST /api/v1/hunch/{dossier_id}/review
- GET  /api/v1/hunch/dossiers

All endpoints enforce:
- ``unilateral_execution = False`` & ``mode = "SHADOW_PAPER"``.
- Supervisory Audit Lens read-only lock (HTTP 403 on mutations).
- Strict role-boundary & Active-Hat enforcement (Directive R-06).
- Zero mutation to live SCMA capital ledgers or IFAS outbox.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import decode_access_token
from app.domain.authority_tiers import normalize_role_token
from app.domain.shadow_hunch_service import (
    ShadowHunchError,
    get_shadow_hunch_service,
)

hunch_router = APIRouter(prefix="/api/v1/hunch", tags=["Shadow Paper Hunch Research Studio"])


class HunchEvaluateRequest(BaseModel):
    hypothesis: str
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    scma_id: Optional[str] = None
    vertical_hint: Optional[str] = None
    quoted_price_cents: Optional[int] = Field(None, ge=1, le=99)
    modeled_prob_cents: Optional[int] = Field(None, ge=1, le=99)
    modeled_prob_bps: Optional[int] = Field(None, ge=100, le=9900)
    fee_cents: Optional[int] = Field(None, ge=0, le=20)


class ShadowBidRequest(BaseModel):
    virtual_stake_cents: int = Field(10_000, ge=100, le=500_000)
    entry_quote_cents: Optional[int] = Field(None, ge=1, le=99)
    side: str = "YES"
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    scma_id: Optional[str] = None
    simulated_outcome: Optional[str] = None


class LiveClearanceRequest(BaseModel):
    scma_id: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    rationale: Optional[str] = ""


class HunchReviewRequest(BaseModel):
    decision: str
    actor_role: Optional[str] = None
    actor_id: Optional[str] = None
    notes: Optional[str] = ""


def _reject_supervisory_mutation(x_supervisory_mode: Optional[str]) -> None:
    if x_supervisory_mode and x_supervisory_mode.strip().lower() in {
        "read-only",
        "readonly",
        "true",
        "1",
        "supervisory",
    }:
        raise HTTPException(
            status_code=403,
            detail="SUPERVISORY_READ_ONLY_INSPECTION: Mutations are disabled while Supervisory Audit Lens is active.",
        )


def _resolve_caller(
    *,
    authorization: Optional[str],
    x_active_hat: Optional[str],
    x_actor_role: Optional[str],
    x_actor_id: Optional[str],
    body_role: Optional[str] = None,
    body_actor_id: Optional[str] = None,
    default_role: str = "MEMBER_USER",
) -> tuple[str, str]:
    role = x_active_hat or x_actor_role or body_role or default_role
    actor_id = x_actor_id or body_actor_id or ""

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        claims = decode_access_token(token)
        if not claims:
            raise HTTPException(status_code=403, detail="Invalid or expired identity token.")
        role = str(claims.get("active_hat") or claims.get("role") or role)
        actor_id = str(claims.get("sub") or claims.get("user_id") or actor_id)

    return normalize_role_token(role), actor_id.strip()


def _lookup_member_state(scma_id: Optional[str]) -> Dict[str, Any]:
    """Read-only lookup of a member's certification_level and risk_dial state (zero mutation)."""
    from app.api.v1.portal_router import get_member_state

    return get_member_state(user_id=None, scma_id=scma_id)


@hunch_router.post("/evaluate")
def evaluate_hunch_api(
    request: HunchEvaluateRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    _reject_supervisory_mutation(x_supervisory_mode)
    role, actor_id = _resolve_caller(
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        body_role=request.actor_role,
        body_actor_id=request.actor_id,
    )
    scma_id = (request.scma_id or "SCMA-ELEANOR_-B2B31C9E").strip()
    try:
        return get_shadow_hunch_service().evaluate_hunch(
            hypothesis=request.hypothesis,
            actor_id=actor_id or scma_id,
            actor_role=role,
            scma_id=scma_id,
            vertical_hint=request.vertical_hint,
            quoted_price_cents=request.quoted_price_cents,
            modeled_prob_cents=request.modeled_prob_cents,
            modeled_prob_bps=request.modeled_prob_bps,
            fee_cents=request.fee_cents,
        )
    except ShadowHunchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_http_detail()) from exc


@hunch_router.post("/{dossier_id}/shadow-bid")
def place_shadow_bid_api(
    dossier_id: str,
    request: ShadowBidRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    _reject_supervisory_mutation(x_supervisory_mode)
    role, actor_id = _resolve_caller(
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        body_role=request.actor_role,
        body_actor_id=request.actor_id,
    )
    try:
        return get_shadow_hunch_service().place_shadow_bid(
            dossier_id,
            virtual_stake_cents=request.virtual_stake_cents,
            entry_quote_cents=request.entry_quote_cents,
            side=request.side,
            actor_id=actor_id or request.scma_id or "",
            actor_role=role,
            simulated_outcome=request.simulated_outcome,
        )
    except ShadowHunchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_http_detail()) from exc


@hunch_router.post("/{dossier_id}/request-live-clearance")
def request_live_clearance_api(
    dossier_id: str,
    request: LiveClearanceRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    _reject_supervisory_mutation(x_supervisory_mode)
    role, actor_id = _resolve_caller(
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        body_role=request.actor_role,
        body_actor_id=request.actor_id,
    )
    svc = get_shadow_hunch_service()
    try:
        existing = svc.get_dossier(dossier_id)
        target_scma = (request.scma_id or existing["scma_id"]).strip()
        member_state = _lookup_member_state(target_scma)
        return svc.request_live_clearance(
            dossier_id,
            member_state=member_state,
            actor_id=actor_id or target_scma,
            actor_role=role,
            rationale=request.rationale or "",
        )
    except ShadowHunchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_http_detail()) from exc


@hunch_router.post("/{dossier_id}/review")
def review_hunch_clearance_api(
    dossier_id: str,
    request: HunchReviewRequest,
    role: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_pdeue_role: Optional[str] = Header(None, alias="X-PDEUE-Role"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    _reject_supervisory_mutation(x_supervisory_mode)
    resolved_role, actor_id = _resolve_caller(
        authorization=authorization,
        x_active_hat=x_pdeue_role or x_active_hat,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        body_role=request.actor_role or role,
        body_actor_id=request.actor_id,
        default_role="",
    )
    try:
        return get_shadow_hunch_service().review_clearance(
            dossier_id,
            decision=request.decision,
            actor_role=resolved_role,
            actor_id=actor_id or resolved_role,
            notes=request.notes or "",
        )
    except ShadowHunchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_http_detail()) from exc


@hunch_router.get("/dossiers")
def list_hunch_dossiers_api(
    scma_id: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    clearance_status: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_pdeue_role: Optional[str] = Header(None, alias="X-PDEUE-Role"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
) -> Dict[str, Any]:
    resolved_role, _ = _resolve_caller(
        authorization=authorization,
        x_active_hat=x_pdeue_role or x_active_hat,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        body_role=role,
        default_role="MEMBER_USER",
    )
    try:
        return get_shadow_hunch_service().list_dossiers(
            actor_role=resolved_role,
            scma_id=scma_id,
            clearance_status=clearance_status,
        )
    except ShadowHunchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_http_detail()) from exc
