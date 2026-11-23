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

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from app.domain.member_onboarding import (
    ALLOWED_HOUSES,
    ALLOWED_ROLE_TIERS,
    InviteTokenError,
    OnboardingValidationError,
    get_onboarding_service,
)

onboarding_router = APIRouter(prefix="/api/v1/onboarding", tags=["Onboarding"])


class ActivateInviteRequest(BaseModel):
    token: str


class CertifyMemberRequest(BaseModel):
    scma_id: Optional[str] = None
    member_id: Optional[str] = None
    chapter_completed: int = 6
    quiz_passed: bool = False
    correct_answers: int = 0
    total_questions: int = 3


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


@onboarding_router.post("/activate")
def activate_member_invite(req: ActivateInviteRequest) -> Dict[str, Any]:
    """
    Stage 2: Validate and consume a single-use 48-hour invite activation token.
    Rejects unknown, expired, or already-used tokens fail-closed.
    """
    svc = get_onboarding_service()
    try:
        return svc.activate_invite_token(req.token)
    except InviteTokenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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
