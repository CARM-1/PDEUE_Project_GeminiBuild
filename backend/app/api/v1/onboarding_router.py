"""
Milestone C1 — 5-Stage Member Onboarding Pipeline API Router.

Endpoints:
- POST /api/v1/onboarding/provision          (Stage 1: Single Member Provisioning)
- POST /api/v1/onboarding/provision/batch    (Stage 1: Atomic JSON / CSV Batch Provisioning)
- GET  /api/v1/onboarding/members            (Admin roster of provisioned members)
- POST /api/v1/onboarding/activate           (Stage 2: Single-Use 48h Invite Activation)
- POST /api/v1/onboarding/certify            (Stage 4: PDEUE University Certification Gate)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel

from app.api.v1.auth_router import _set_session_cookie
from app.domain.authority_tiers import get_active_hat_gateway, normalize_role_token
from app.domain.member_onboarding import (
    ALLOWED_HOUSES,
    ALLOWED_ROLE_TIERS,
    InviteTokenError,
    OnboardingValidationError,
    get_onboarding_service,
)
from app.domain.role_custody_service import get_role_custody_service
from app.domain.session_auth_service import get_session_auth_service, parse_house_number

onboarding_router = APIRouter(prefix="/api/v1/onboarding", tags=["Onboarding"])


class ActivateInviteRequest(BaseModel):
    token: str
    email: Optional[str] = None
    issue_session: bool = True


class CertifyMemberRequest(BaseModel):
    scma_id: Optional[str] = None
    member_id: Optional[str] = None
    chapter_completed: int = 6
    quiz_passed: bool = False
    correct_answers: int = 0
    total_questions: int = 3


def _resolve_onboarding_actor(
    *,
    x_actor_role: Optional[str],
    x_actor_id: Optional[str],
    x_house_id: Optional[str],
    authorization: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> tuple[str, str, Optional[int]]:
    auth_session = getattr(request.state, "auth_session", None) if request is not None else None
    role = (
        x_actor_role
        or (auth_session.active_hat if auth_session is not None else "")
        or (str(payload.get("actor_role") or "") if isinstance(payload, dict) else "")
    )
    actor_id = (
        x_actor_id
        or (auth_session.user_id if auth_session is not None else "")
        or (str(payload.get("actor_id") or "") if isinstance(payload, dict) else "")
    )
    if authorization and authorization.lower().startswith("bearer "):
        from app.core.security import decode_access_token

        token = authorization.split(" ", 1)[1].strip()
        claims = decode_access_token(token)
        if not claims:
            raise HTTPException(status_code=403, detail="INVALID_OR_EXPIRED_ACTIVE_HAT_TOKEN")
        hat = normalize_role_token(claims.get("active_hat") or claims.get("role"))
        if claims.get("session_id"):
            get_active_hat_gateway().verify_token(token, required_hats={hat}, action="ONBOARDING_DELEGATION")
        role = hat
        actor_id = str(claims.get("sub") or claims.get("user_id") or actor_id or "jwt_principal")
    actor_house: Optional[int] = None
    raw_h = (
        x_house_id
        or (payload.get("actor_house_id") if isinstance(payload, dict) else None)
        or (auth_session.house_id if auth_session is not None else None)
    )
    if raw_h is not None and raw_h != "":
        parsed_h = parse_house_number(str(raw_h))
        if parsed_h is None:
            raise HTTPException(status_code=403, detail="Invalid X-House-ID header")
        actor_house = parsed_h
    return normalize_role_token(role), (actor_id or normalize_role_token(role) or "anonymous"), actor_house


@onboarding_router.get("/schema")
def get_onboarding_schema() -> Dict[str, Any]:
    """Return allowed houses, role tiers, risk bounds, and ADR-011 token pattern."""
    return {
        "lineage_houses": list(ALLOWED_HOUSES),
        "role_tiers": list(ALLOWED_ROLE_TIERS),
        "risk_dial_pct_range": [0.50, 2.00],
        "bank_ref_format": "EXT-REF-[ENTITY]-****[LAST4]",
        "invite_ttl_hours": 48,
        "ifas_portal_host": "accounting.narratix.io",
    }


@onboarding_router.get("/members")
def list_onboarded_members() -> Dict[str, Any]:
    """Return all provisioned members and their certification / HWM status."""
    svc = get_onboarding_service()
    members = svc.list_members()
    return {"count": len(members), "members": members}


@onboarding_router.post("/provision", status_code=201)
def provision_single_member(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Stage 1: Provision a single member SCMA with ADR-008 exact integer cents,
    ADR-011 opaque bank reference token, ADR-012 HWM initialization, and a
    cryptographically random single-use 48-hour invite activation token.
    """
    svc = get_onboarding_service()
    try:
        return svc.provision_member(payload)
    except OnboardingValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@onboarding_router.post("/provision/batch", status_code=201)
def provision_batch_members(
    payload: Union[Dict[str, Any], List[Dict[str, Any]]] = Body(...),
) -> Dict[str, Any]:
    """
    Stage 1 Batch Provisioning (JSON array or CSV payload).
    Fail-closed atomic validation: if any row violates ADR-008 or ADR-011,
    the entire batch is rejected with HTTP 422 and zero records are persisted.
    """
    svc = get_onboarding_service()
    try:
        if isinstance(payload, list):
            return svc.provision_batch(payload, from_csv=False)
        if not isinstance(payload, dict):
            raise OnboardingValidationError("Batch payload must be a JSON object or JSON array.")

        fmt = str(payload.get("format") or "").strip().lower()
        if fmt == "csv" or "csv_text" in payload:
            csv_text = payload.get("csv_text")
            if not isinstance(csv_text, str):
                raise OnboardingValidationError("csv_text must be a string when using CSV batch format.")
            rows = svc.parse_csv_rows(csv_text)
            return svc.provision_batch(rows, from_csv=True)

        members = payload.get("members")
        if not isinstance(members, list):
            raise OnboardingValidationError(
                "Batch payload must provide either a 'members' JSON array or 'csv_text'."
            )
        return svc.provision_batch(members, from_csv=False)
    except OnboardingValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@onboarding_router.get("/invite-preview")
def preview_member_invite(token: str = Query(..., min_length=4)) -> Dict[str, Any]:
    """Read-only Stage 2 invite preview for the senior-friendly /activate portal."""
    svc = get_onboarding_service()
    try:
        return svc.preview_invite_token(token)
    except InviteTokenError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "code": exc.code},
        ) from exc


@onboarding_router.post("/activate")
def activate_member_invite(
    req: ActivateInviteRequest,
    request: Request,
    response: Response,
) -> Dict[str, Any]:
    """
    Stage 2: Validate and consume a single-use 48-hour invite activation token.
    Automatically provisions the member on PR #98's private family allowlist (`AuthUserModel`),
    optionally sets a signed HttpOnly `pdeue_session` cookie bound strictly to their SCMA,
    and rejects unknown, expired, or already-used tokens fail-closed.
    """
    svc = get_onboarding_service()
    try:
        result = svc.activate_invite_token(req.token, email=req.email)
    except InviteTokenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    session_issued = False
    session_dict: Optional[Dict[str, Any]] = None
    if req.issue_session:
        auth_svc = get_session_auth_service()
        if getattr(auth_svc, "_engine", None) is getattr(svc, "_engine", None):
            issued = auth_svc.issue_session_for_user(
                result["member"]["member_id"],
                auth_method="INVITE_ACTIVATION",
            )
            if issued is not None:
                ctx, signed_cookie = issued
                _set_session_cookie(
                    response,
                    request=request,
                    signed_cookie=signed_cookie,
                    active_hat=ctx.active_hat,
                )
                session_issued = True
                session_dict = ctx.to_dict()

    result["session_issued"] = session_issued
    if session_dict is not None:
        result["session"] = session_dict
    return result


@onboarding_router.post("/certify")
def certify_member_stewardship(req: CertifyMemberRequest) -> Dict[str, Any]:
    """
    Stage 4: Upgrade a PENDING_TUTOR_CERTIFICATION member to ACTIVE
    (STEWARDSHIP_L1_CERTIFIED) after passing Chapter 6 on /companion.
    """
    svc = get_onboarding_service()
    try:
        return svc.certify_member(
            scma_id=req.scma_id,
            member_id=req.member_id,
            chapter_completed=req.chapter_completed,
            quiz_passed=req.quiz_passed,
            correct_answers=req.correct_answers,
            total_questions=req.total_questions,
        )
    except OnboardingValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


# =============================================================================
# PR #81 / PR #99 — 3-STAGE DELEGATED ONBOARDING, TWO-PARTY CO-SIGN & RATIFICATION
# =============================================================================


@onboarding_router.get("/delegation-config")
def get_delegated_onboarding_config() -> Dict[str, Any]:
    """Return Chief Admin delegation scope (ADMIN_ONLY default), admission authority mode (CHIEF_ADMIN_SOLO default), per-House flags, and Genealogical Board state."""
    return get_role_custody_service().get_policy_controls()


@onboarding_router.post("/delegation-config")
def update_delegated_onboarding_config(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """Chief Administrator controls for delegated intake scope, admission authority mode, per-House toggles, and Genealogical Board."""
    actor_role, actor_id, _ = _resolve_onboarding_actor(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        authorization=authorization,
        payload=payload,
        request=request,
    )
    return get_role_custody_service().update_delegation_config(
        delegated_onboarding_scope=payload.get("delegated_onboarding_scope"),
        admission_authority_mode=payload.get("admission_authority_mode"),
        house_delegation_flags=payload.get("house_delegation_flags"),
        genealogical_board_enabled=payload.get("genealogical_board_enabled"),
        genealogical_board_quorum=payload.get("genealogical_board_quorum"),
        reason=str(payload.get("reason") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@onboarding_router.post("/delegated-submit", status_code=201)
def submit_delegated_onboarding_dossier(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """Stage 1: Authorized ranked officer submits admission dossier strictly into PENDING_RATIFICATION."""
    actor_role, actor_id, actor_house = _resolve_onboarding_actor(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        authorization=authorization,
        payload=payload,
        request=request,
    )
    return get_role_custody_service().submit_delegated_dossier(
        payload,
        actor_role=actor_role,
        actor_id=actor_id,
        actor_house_id=actor_house,
    )


@onboarding_router.get("/dossiers")
def list_onboarding_dossiers(
    status: Optional[str] = Query(None),
    house_id: Optional[int] = Query(None),
) -> Dict[str, Any]:
    """List submitted delegated onboarding dossiers."""
    dossiers = get_role_custody_service().list_dossiers(status=status, house_id=house_id)
    return {"count": len(dossiers), "dossiers": dossiers}


@onboarding_router.get("/dossiers/{dossier_id}")
def get_onboarding_dossier(dossier_id: str) -> Dict[str, Any]:
    """Fetch one delegated onboarding dossier by ID."""
    return {"dossier": get_role_custody_service().get_dossier(dossier_id)}


@onboarding_router.post("/dossiers/{dossier_id}/board-vote")
def cast_genealogical_board_vote(
    dossier_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """Stage 2 (Optional): Genealogical Admissions Board vote by HOUSE_GENEALOGIST / H2."""
    actor_role, actor_id, actor_house = _resolve_onboarding_actor(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        authorization=authorization,
        payload=payload,
        request=request,
    )
    return get_role_custody_service().cast_board_vote(
        dossier_id=dossier_id,
        vote=str(payload.get("vote") or ""),
        rationale=str(payload.get("rationale") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
        actor_house_id=actor_house,
    )


@onboarding_router.post("/dossiers/{dossier_id}/cosign")
def cosign_onboarding_dossier(
    dossier_id: str,
    request: Request,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """PR #99 Two-Party Admission Co-Sign strictly for authorized F2-H (assigned House) or CHIEF_ADMIN audit inspection."""
    body = payload or {}
    actor_role, actor_id, actor_house = _resolve_onboarding_actor(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        authorization=authorization,
        payload=body,
        request=request,
    )
    return get_role_custody_service().cosign_dossier(
        dossier_id=dossier_id,
        notes=str(body.get("notes") or body.get("reason") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
        actor_house_id=actor_house,
    )


@onboarding_router.post("/dossiers/{dossier_id}/ratify")
def ratify_onboarding_dossier(
    dossier_id: str,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """Stage 2 -> Stage 3: Chief Admin ratification + dual-plane PDEUE SCMA + signed IFAS outbox handoff."""
    body = payload or {}
    actor_role, actor_id, _ = _resolve_onboarding_actor(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        authorization=authorization,
        payload=body,
    )
    return get_role_custody_service().ratify_dossier(
        dossier_id=dossier_id,
        decision_notes=str(body.get("decision_notes") or body.get("reason") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@onboarding_router.post("/dossiers/{dossier_id}/reject")
def reject_onboarding_dossier(
    dossier_id: str,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """Chief Admin rejection of an onboarding dossier."""
    body = payload or {}
    actor_role, actor_id, _ = _resolve_onboarding_actor(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        authorization=authorization,
        payload=body,
    )
    return get_role_custody_service().reject_dossier(
        dossier_id=dossier_id,
        reason=str(body.get("reason") or body.get("decision_notes") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
    )


@onboarding_router.post("/dossiers/{dossier_id}/request-proof")
def request_onboarding_dossier_proof(
    dossier_id: str,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """Request additional genealogical/kinship proof on an onboarding dossier."""
    body = payload or {}
    actor_role, actor_id, _ = _resolve_onboarding_actor(
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_house_id=x_house_id,
        authorization=authorization,
        payload=body,
    )
    return get_role_custody_service().request_dossier_proof(
        dossier_id=dossier_id,
        proof_request=str(body.get("proof_request") or body.get("reason") or ""),
        actor_role=actor_role,
        actor_id=actor_id,
    )

