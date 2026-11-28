"""
Milestone PR #81 — Relational Multi-User Role Provisioning Registry,
Atomic Promotion/Demotion & Anti-Tribalism Custody Engine, Scoped Custodial
Lookup, and 3-Stage Delegated Onboarding / Genealogical Ratification.

Architectural Invariants Preserved:
- ADR-008: Strict 64-bit integer-cent accounting (zero float currency math).
- ADR-011: Zero banking credentials or SSNs in PDEUE; opaque EXT-REF tokens only;
  signed HMAC-SHA256 JSON-LD MEMBER_ADMISSION_RATIFIED outbox handoff to IFAS.
- ADR-012 / Rule A14: High-Water Mark initialized to seed_cents; 100% SCMA loss isolation.
- Directive R-06 & R-12: Active-Hat immediate privilege sync; strict server-side
  HTTP 403 scope isolation; Class T ($****.** / SCMA-MEM-****) masking enforced.
- Founder Apex Immunity: Subordinate tiers cannot demote, revoke, or supersede Founder.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
import uuid

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    AccountModel,
    AccountingOutboxEventModel,
    AuditLogRecordModel,
    CustodialAssignmentModel,
    DelegatedOnboardingDossierModel,
    EnclavePolicyControlModel,
    LineageHouseMemberModel,
    LineageHouseModel,
    OnboardingMemberModel,
    UserModel,
    UserRoleAssignmentModel,
)
from app.db.session import Base, SessionLocal, engine as default_engine
from app.domain.authority_tiers import (
    enforce_founder_immunity,
    get_active_hat_gateway,
    get_governance_audit_log,
    is_chief_admin_role,
    is_class_t_role,
    is_founder_target,
    normalize_role_token,
)
from app.domain.enclave_governance import format_cents
from app.domain.lineage_hierarchy import LineageHierarchyService, get_lineage_service
from app.domain.member_onboarding import (
    FORBIDDEN_BANKING_KEYS,
    MemberOnboardingService,
    OnboardingValidationError,
    get_onboarding_service,
    validate_exact_cents,
    validate_lineage_house,
    validate_opaque_bank_ref,
    validate_optional_email,
    validate_risk_dial_bps,
)
from app.domain.session_auth_service import provision_member_auth_allowlist_in_session

FOUNDER_MEMBER_ID = "USR-founder_ch-C8575D7E"
FOUNDER_SCMA_ID = "SCMA-FOUNDER_-C8575D7E"

SINGLE_SEAT_ROLES: frozenset[str] = frozenset({"CHIEF_ADMIN", "T3", "F3"})
MULTI_SEAT_ROLES: frozenset[str] = frozenset(
    {
        "T1",
        "T2",
        "T2-HOUSEHOLD",
        "F1",
        "F2-H",
        "F2-A",
        "H1",
        "H2",
        "HOUSE_GENEALOGIST",
        "MEMBER_USER",
    }
)
ALL_REGISTRY_ROLES: frozenset[str] = SINGLE_SEAT_ROLES | MULTI_SEAT_ROLES

CUSTODIAL_MENTOR_ROLES: Tuple[str, ...] = ("F1", "F2-A", "F2-H", "H2")
CUSTODIAL_LOOKUP_OFFICER_ROLES: frozenset[str] = frozenset(
    {"CHIEF_ADMIN", "F3", "F2-H", "F2-A", "F1", "H2", "H1", "HOUSE_GENEALOGIST"}
)
DELEGATED_SUBMITTER_ROLES: frozenset[str] = frozenset(
    {"CHIEF_ADMIN", "H2", "H1", "F2-H", "HOUSE_GENEALOGIST"}
)
GENEALOGICAL_BOARD_ROLES: frozenset[str] = frozenset(
    {"CHIEF_ADMIN", "HOUSE_GENEALOGIST", "H2"}
)

ROLE_RANK: Dict[str, int] = {
    "MEMBER_USER": 10,
    "T1": 20,
    "H1": 25,
    "F1": 30,
    "HOUSE_GENEALOGIST": 35,
    "T2-HOUSEHOLD": 40,
    "T2": 45,
    "F2-A": 50,
    "F2-H": 55,
    "H2": 60,
    "T3": 80,
    "F3": 85,
    "CHIEF_ADMIN": 100,
}

CUSTODY_MODE_INTRA_HOUSE = "INTRA_HOUSE"
CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL = "CROSS_HOUSE_ANTI_TRIBAL"
VALID_CUSTODY_MODES = (CUSTODY_MODE_INTRA_HOUSE, CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL)

DELEGATION_SCOPE_ADMIN_ONLY = "ADMIN_ONLY"
DELEGATION_SCOPE_PER_HOUSE = "PER_HOUSE"
DELEGATION_SCOPE_ENCLAVE_WIDE = "ENCLAVE_WIDE"
VALID_DELEGATION_SCOPES = (
    DELEGATION_SCOPE_ADMIN_ONLY,
    DELEGATION_SCOPE_PER_HOUSE,
    DELEGATION_SCOPE_ENCLAVE_WIDE,
)

ADMISSION_MODE_CHIEF_ADMIN_SOLO = "CHIEF_ADMIN_SOLO"
ADMISSION_MODE_TWO_PARTY_COSIGN = "TWO_PARTY_COSIGN"
VALID_ADMISSION_AUTHORITY_MODES = (
    ADMISSION_MODE_CHIEF_ADMIN_SOLO,
    ADMISSION_MODE_TWO_PARTY_COSIGN,
)

DOSSIER_PENDING_RATIFICATION = "PENDING_RATIFICATION"
DOSSIER_BOARD_RECOMMENDED = "BOARD_RECOMMENDED"
DOSSIER_PROOF_REQUESTED = "PROOF_REQUESTED"
DOSSIER_RATIFIED_PROVISIONED = "RATIFIED_PROVISIONED"
DOSSIER_REJECTED = "REJECTED"

_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CONTIGUOUS_9_DIGITS = re.compile(r"(?<!\d)\d{9,17}(?!\d)")
_ROUTING_OR_ACCT_HINT = re.compile(r"(?i)\b(?:routing\s*#|aba\s*#?|swift|iban|acct\s*#?|ssn|social\s+security)\b")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_registry_role(raw: Optional[str]) -> str:
    """Normalize any role/sub-tier string to its canonical PR #81 registry token."""
    if not raw:
        return ""
    norm = normalize_role_token(raw)
    if norm == "CHIEF_ADMINISTRATOR":
        return "CHIEF_ADMIN"
    if norm == "PERSONAL_SCMA":
        return "MEMBER_USER"
    return norm


def _validate_registry_role(raw: Optional[str]) -> str:
    token = canonical_registry_role(raw)
    if token not in ALL_REGISTRY_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported role_token '{raw}'. Allowed roles: {', '.join(sorted(ALL_REGISTRY_ROLES))}.",
        )
    return token


def _validate_house_id(house_id: Optional[Any], *, required: bool = False) -> Optional[int]:
    if house_id is None or house_id == "":
        if required:
            raise HTTPException(status_code=422, detail="house_id (1..12) is required.")
        return None
    if isinstance(house_id, bool):
        raise HTTPException(status_code=422, detail="house_id must be an integer between 1 and 12.")
    try:
        if isinstance(house_id, str):
            clean = house_id.strip().upper().replace("HOUSE-", "")
            hid = int(clean)
        else:
            hid = int(house_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid house_id '{house_id}'.") from exc
    if hid < 1 or hid > 12:
        raise HTTPException(status_code=422, detail="house_id must be between 1 and 12.")
    return hid


def _reject_pii_and_banking_payload(value: Any, *, path: str = "") -> None:
    """Fail closed (HTTP 422) if any bank credential, routing/account number, or SSN appears."""
    if isinstance(value, dict):
        for k, v in value.items():
            key_lower = str(k).strip().lower()
            if key_lower in FORBIDDEN_BANKING_KEYS:
                raise HTTPException(
                    status_code=422,
                    detail=f"ADR-011 / PII air-gap violation: forbidden field '{k}' is permanently prohibited in PDEUE.",
                )
            _reject_pii_and_banking_payload(v, path=key_lower)
    elif isinstance(value, list):
        for item in value:
            _reject_pii_and_banking_payload(item, path=path)
    elif isinstance(value, str):
        if _SSN_PATTERN.search(value):
            raise HTTPException(
                status_code=422,
                detail="ADR-011 / PII air-gap violation: SSN patterns are strictly prohibited in PDEUE.",
            )
        if path != "bank_ref_token" and _CONTIGUOUS_9_DIGITS.search(value):
            raise HTTPException(
                status_code=422,
                detail="ADR-011 / PII air-gap violation: raw 9+ digit banking or government ID numbers are strictly prohibited.",
            )
        if path != "bank_ref_token" and _ROUTING_OR_ACCT_HINT.search(value) and re.search(r"\d{5,}", value):
            raise HTTPException(
                status_code=422,
                detail="ADR-011 / PII air-gap violation: raw banking routing/account identifiers are strictly prohibited.",
            )


class RoleCustodyDelegationService:
    """
    Persistent SQLAlchemy coordinator for:
    1. Multi-user role provisioning (single-seat vs multi-seat + atomic succession)
    2. Atomic promotion/demotion & anti-tribalism custodial pairing (zero orphans)
    3. Server-side scoped custodial lookup (with Directive R-12 Class T masking)
    4. 3-Stage Delegated Onboarding & Genealogical Ratification + signed IFAS outbox
    """

    def __init__(
        self,
        *,
        session_factory: Optional[Callable[[], Session]] = None,
        bind_engine: Any = None,
        lineage_service: Optional[LineageHierarchyService] = None,
        onboarding_service: Optional[MemberOnboardingService] = None,
        accounting_gateway: Optional[Any] = None,
        register_hat_provider: bool = False,
    ) -> None:
        self._lock = RLock()
        self._session_factory = session_factory or SessionLocal
        self._engine = bind_engine or default_engine
        self._lineage = lineage_service or get_lineage_service()
        self._onboarding = onboarding_service
        self._accounting_gateway = accounting_gateway
        self._initialized = False
        self._ensure_ready()
        if register_hat_provider:
            get_active_hat_gateway().set_dynamic_role_provider(self.get_active_roles_for_member_or_none)

    def _get_onboarding_service(self) -> MemberOnboardingService:
        if self._onboarding is not None:
            return self._onboarding
        return get_onboarding_service()

    def _get_accounting_gateway(self) -> Any:
        if self._accounting_gateway is not None:
            return self._accounting_gateway
        from app.api.v1.accounting_router import global_accounting_gateway

        return global_accounting_gateway

    def _ensure_ready(self) -> None:
        with self._lock:
            if self._initialized:
                try:
                    with self._session_factory() as db:
                        if db.get(EnclavePolicyControlModel, "GLOBAL") is not None:
                            return
                except Exception:
                    pass
            Base.metadata.create_all(bind=self._engine)
            with self._session_factory() as db:
                self._seed_defaults(db)
            self._initialized = True

    def _seed_defaults(self, db: Session) -> None:
        now = _utc_now()
        policy = db.get(EnclavePolicyControlModel, "GLOBAL")
        if policy is None:
            default_flags = {str(h): False for h in range(1, 13)}
            db.add(
                EnclavePolicyControlModel(
                    config_id="GLOBAL",
                    custody_assignment_mode=CUSTODY_MODE_INTRA_HOUSE,
                    delegated_onboarding_scope=DELEGATION_SCOPE_ADMIN_ONLY,
                    admission_authority_mode=ADMISSION_MODE_CHIEF_ADMIN_SOLO,
                    genealogical_board_enabled=0,
                    genealogical_board_quorum=2,
                    house_delegation_flags_json=json.dumps(default_flags),
                    updated_by="SYSTEM_INIT",
                    updated_at_utc=now,
                    reason="Initial fail-closed Ring 1 Alpha defaults (INTRA_HOUSE custody, ADMIN_ONLY onboarding, CHIEF_ADMIN_SOLO admission).",
                )
            )

        # Seed baseline role assignments only when the table is completely empty
        if db.query(UserRoleAssignmentModel).count() == 0:
            seeded_roles = [
                ("ROLE-SEED-CHIEF-ADMIN", FOUNDER_MEMBER_ID, "CHIEF_ADMIN", 1, "Founding Sovereign Settlor seat"),
                ("ROLE-SEED-ELEANOR-F2H", "USR-eleanor_va-B2B31C9E", "F2-H", 1, "Founding Head of Household (House 01)"),
                ("ROLE-SEED-ELEANOR-H2", "USR-eleanor_va-B2B31C9E", "H2", 1, "Founding House 01 Leader"),
                ("ROLE-SEED-JULIAN-MEM", "USR-julian_va-A1F98B21", "MEMBER_USER", 2, "Founding Custodial Apprentice (House 02)"),
            ]
            for aid, mid, role_tok, hid, reason in seeded_roles:
                db.add(
                    UserRoleAssignmentModel(
                        assignment_id=aid,
                        member_id=mid,
                        role_token=role_tok,
                        house_id=hid,
                        status="ACTIVE",
                        assigned_by="SYSTEM_INIT",
                        assigned_at_utc=now,
                        revoked_at_utc=None,
                        reason=reason,
                    )
                )

        # Seed baseline custodial assignment when table is empty
        if db.query(CustodialAssignmentModel).count() == 0:
            db.add(
                CustodialAssignmentModel(
                    custody_id="CUST-SEED-JULIAN-01",
                    custodian_member_id="USR-eleanor_va-B2B31C9E",
                    custodian_role="F2-H",
                    charge_member_id="USR-julian_va-A1F98B21",
                    charge_scma_id="SCMA-JULIAN_-A1F98B21",
                    charge_house_id=2,
                    assignment_mode=CUSTODY_MODE_INTRA_HOUSE,
                    active=1,
                    assigned_by="SYSTEM_INIT",
                    assigned_at_utc=now,
                    ended_at_utc=None,
                    reason="Baseline founding custodial apprenticeship",
                )
            )

        db.commit()

    def _require_chief_admin(
        self,
        *,
        actor_role: Optional[str],
        actor_id: str,
        action: str,
        target_id: str,
    ) -> None:
        norm = normalize_role_token(actor_role)
        if not is_chief_admin_role(norm):
            get_governance_audit_log().record(
                event_type="ROLE_BOUNDARY_DENIED",
                actor_id=actor_id or "unknown",
                actor_role=norm or "UNSPECIFIED",
                target_id=target_id,
                action=action,
                outcome="DENIED_CHIEF_ADMIN_REQUIRED",
                http_status=403,
                detail=f"Role '{norm or 'UNSPECIFIED'}' cannot execute {action}; Chief Administrator required.",
            )
            raise HTTPException(
                status_code=403,
                detail=f"CHIEF_ADMIN_REQUIRED: Only the Chief Administrator may execute {action}.",
            )

    def _record_db_audit(
        self,
        db: Session,
        *,
        tenant_id: str,
        actor_id: str,
        action: str,
        payload: Dict[str, Any],
        recorded_at: str,
    ) -> None:
        payload_str = json.dumps(payload, sort_keys=True)
        prev_hash = "0" * 64
        digest = hashlib.sha256(
            f"{prev_hash}|{tenant_id}|{actor_id}|{action}|{payload_str}".encode("utf-8")
        ).hexdigest()
        db.add(
            AuditLogRecordModel(
                entry_id=f"AUD-PR81-{uuid.uuid4().hex[:10].upper()}",
                tenant_id=tenant_id,
                actor_id=actor_id,
                action=action,
                prev_hash=prev_hash,
                entry_hash=digest,
                payload=payload_str,
                recorded_at=recorded_at,
            )
        )

    # ------------------------------------------------------------------
    # Serialization Helpers
    # ------------------------------------------------------------------

    def _serialize_role(self, row: UserRoleAssignmentModel) -> Dict[str, Any]:
        return {
            "assignment_id": row.assignment_id,
            "member_id": row.member_id,
            "role_token": row.role_token,
            "seat_class": "SINGLE_SEAT" if row.role_token in SINGLE_SEAT_ROLES else "MULTI_SEAT",
            "house_id": row.house_id,
            "lineage_code": f"HOUSE-{row.house_id:02d}" if row.house_id else "ENCLAVE",
            "status": row.status,
            "assigned_by": row.assigned_by,
            "assigned_at_utc": row.assigned_at_utc,
            "revoked_at_utc": row.revoked_at_utc,
            "reason": row.reason or "",
        }

    def _serialize_custody(self, row: CustodialAssignmentModel) -> Dict[str, Any]:
        return {
            "custody_id": row.custody_id,
            "custodian_member_id": row.custodian_member_id,
            "custodian_role": row.custodian_role,
            "charge_member_id": row.charge_member_id,
            "charge_scma_id": row.charge_scma_id,
            "charge_house_id": int(row.charge_house_id),
            "charge_lineage_code": f"HOUSE-{int(row.charge_house_id):02d}",
            "assignment_mode": row.assignment_mode,
            "active": bool(row.active),
            "assigned_by": row.assigned_by,
            "assigned_at_utc": row.assigned_at_utc,
            "ended_at_utc": row.ended_at_utc,
            "reason": row.reason or "",
        }

    def _serialize_policy(self, row: EnclavePolicyControlModel) -> Dict[str, Any]:
        try:
            raw_flags = json.loads(row.house_delegation_flags_json or "{}")
        except Exception:
            raw_flags = {}
        house_flags = {str(h): bool(raw_flags.get(str(h), False)) for h in range(1, 13)}
        admission_mode = (
            getattr(row, "admission_authority_mode", None) or ADMISSION_MODE_CHIEF_ADMIN_SOLO
        )
        return {
            "custody_assignment_mode": row.custody_assignment_mode,
            "anti_tribalism_active": row.custody_assignment_mode == CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL,
            "delegated_onboarding_scope": row.delegated_onboarding_scope,
            "admission_authority_mode": admission_mode,
            "two_party_cosign_required": admission_mode == ADMISSION_MODE_TWO_PARTY_COSIGN,
            "genealogical_board_enabled": bool(row.genealogical_board_enabled),
            "genealogical_board_quorum": int(row.genealogical_board_quorum),
            "house_delegation_flags": house_flags,
            "updated_by": row.updated_by,
            "updated_at_utc": row.updated_at_utc,
            "reason": row.reason or "",
        }

    def _serialize_dossier(self, row: DelegatedOnboardingDossierModel) -> Dict[str, Any]:
        try:
            votes = json.loads(row.board_votes_json or "[]")
        except Exception:
            votes = []
        approve_count = sum(1 for v in votes if str(v.get("vote")).upper() == "APPROVE")
        reject_count = sum(1 for v in votes if str(v.get("vote")).upper() == "REJECT")
        proof_count = sum(1 for v in votes if str(v.get("vote")).upper() == "REQUEST_PROOF")
        f2h_cosigned_by = getattr(row, "f2h_cosigned_by", None)
        f2h_cosigned_at = getattr(row, "f2h_cosigned_at_utc", None)
        return {
            "dossier_id": row.dossier_id,
            "applicant_full_name": row.applicant_full_name,
            "applicant_email": getattr(row, "applicant_email", None),
            "applicant_member_id": row.applicant_member_id,
            "target_house_id": int(row.target_house_id),
            "lineage_code": row.lineage_code,
            "kinship_verification": row.kinship_verification,
            "custodial_status": row.custodial_status,
            "is_custodial": bool(row.is_custodial),
            "pay_it_forward_sponsored": bool(row.pay_it_forward_sponsored),
            "sponsor_member_id": row.sponsor_member_id,
            "seed_cents": int(row.seed_cents),
            "seed_formatted": format_cents(int(row.seed_cents)),
            "risk_dial_bps": int(row.risk_dial_bps),
            "bank_ref_token": row.bank_ref_token,
            "due_diligence_attestation": row.due_diligence_attestation,
            "attestation_signature": row.attestation_signature,
            "submitted_by_member_id": row.submitted_by_member_id,
            "submitted_by_role": row.submitted_by_role,
            "submitted_by_house_id": row.submitted_by_house_id,
            "status": row.status,
            "board_votes": votes,
            "board_approve_count": approve_count,
            "board_reject_count": reject_count,
            "board_proof_request_count": proof_count,
            "f2h_cosigned": bool(f2h_cosigned_by and f2h_cosigned_at),
            "f2h_cosigned_by": f2h_cosigned_by,
            "f2h_cosigned_role": getattr(row, "f2h_cosigned_role", None),
            "f2h_cosigned_house_id": getattr(row, "f2h_cosigned_house_id", None),
            "f2h_cosigned_at_utc": f2h_cosigned_at,
            "f2h_cosign_notes": getattr(row, "f2h_cosign_notes", None) or "",
            "f2h_cosign_signature": getattr(row, "f2h_cosign_signature", None),
            "ratified_by": row.ratified_by,
            "ratified_at_utc": row.ratified_at_utc,
            "decision_notes": row.decision_notes or "",
            "provisioned_member_id": row.provisioned_member_id,
            "provisioned_scma_id": row.provisioned_scma_id,
            "assigned_custodian_member_id": row.assigned_custodian_member_id,
            "ifas_outbox_event_id": row.ifas_outbox_event_id,
            "created_at_utc": row.created_at_utc,
            "updated_at_utc": row.updated_at_utc,
        }

    # ------------------------------------------------------------------
    # 2. Relational Multi-User Role & Authority Provisioning Registry
    # ------------------------------------------------------------------

    def get_active_roles_for_member_or_none(self, member_id: str) -> Optional[List[str]]:
        """Return active role tokens for member_id, or None if member has no registry rows."""
        self._ensure_ready()
        if not member_id:
            return None
        with self._session_factory() as db:
            rows = (
                db.query(UserRoleAssignmentModel)
                .filter(UserRoleAssignmentModel.member_id == member_id)
                .all()
            )
            if not rows:
                return None
            active = [r.role_token for r in rows if r.status == "ACTIVE"]
            return active if active else ["MEMBER_USER"]

    def list_role_assignments(
        self,
        *,
        active_only: bool = False,
        role_token: Optional[str] = None,
        member_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        with self._session_factory() as db:
            q = db.query(UserRoleAssignmentModel)
            if active_only:
                q = q.filter(UserRoleAssignmentModel.status == "ACTIVE")
            if role_token:
                q = q.filter(UserRoleAssignmentModel.role_token == canonical_registry_role(role_token))
            if member_id:
                q = q.filter(UserRoleAssignmentModel.member_id == member_id.strip())
            rows = q.order_by(UserRoleAssignmentModel.assigned_at_utc.desc()).all()

            # Build single-seat occupancy summary
            single_seats: Dict[str, Optional[Dict[str, Any]]] = {}
            for seat_role in ("CHIEF_ADMIN", "T3", "F3"):
                holder = (
                    db.query(UserRoleAssignmentModel)
                    .filter(
                        UserRoleAssignmentModel.role_token == seat_role,
                        UserRoleAssignmentModel.status == "ACTIVE",
                    )
                    .first()
                )
                single_seats[seat_role] = self._serialize_role(holder) if holder else None

            return {
                "single_seat_roles": sorted(SINGLE_SEAT_ROLES),
                "multi_seat_roles": sorted(MULTI_SEAT_ROLES),
                "single_seat_holders": single_seats,
                "assignments": [self._serialize_role(r) for r in rows],
            }

    def assign_role(
        self,
        *,
        member_id: str,
        role_token: str,
        house_id: Optional[int] = None,
        atomic_succession: bool = False,
        reason: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = FOUNDER_MEMBER_ID,
    ) -> Dict[str, Any]:
        """Grant a role assignment enforcing strict single-seat uniqueness for CHIEF_ADMIN/T3/F3."""
        self._ensure_ready()
        clean_member = str(member_id or "").strip()
        if not clean_member:
            raise HTTPException(status_code=422, detail="member_id is required.")
        norm_role = _validate_registry_role(role_token)
        resolved_house = _validate_house_id(house_id, required=False)

        # Chief Admin authority required for all role provisioning
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="ASSIGN_ROLE",
            target_id=f"{clean_member}:{norm_role}",
        )

        now = _utc_now()
        superseded_holder: Optional[Dict[str, Any]] = None
        reassigned_charges: List[Dict[str, Any]] = []

        with self._session_factory() as db:
            # Check exact duplicate active assignment
            dup_query = db.query(UserRoleAssignmentModel).filter(
                UserRoleAssignmentModel.member_id == clean_member,
                UserRoleAssignmentModel.role_token == norm_role,
                UserRoleAssignmentModel.status == "ACTIVE",
            )
            if resolved_house is not None:
                dup_query = dup_query.filter(UserRoleAssignmentModel.house_id == resolved_house)
            existing_same = dup_query.first()
            if existing_same is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"DUPLICATE_ACTIVE_ROLE_ASSIGNMENT: {clean_member} already holds active role {norm_role}.",
                )

            # Enforce strict single-seat uniqueness for CHIEF_ADMIN, T3 (CTO), F3 (CRO)
            if norm_role in SINGLE_SEAT_ROLES:
                incumbent = (
                    db.query(UserRoleAssignmentModel)
                    .filter(
                        UserRoleAssignmentModel.role_token == norm_role,
                        UserRoleAssignmentModel.status == "ACTIVE",
                    )
                    .first()
                )
                if incumbent is not None and incumbent.member_id != clean_member:
                    if not atomic_succession:
                        get_governance_audit_log().record(
                            event_type="SINGLE_SEAT_CONFLICT",
                            actor_id=actor_id,
                            actor_role="CHIEF_ADMINISTRATOR",
                            target_id=f"{norm_role}:{clean_member}",
                            action="ASSIGN_ROLE",
                            outcome="CONFLICT_SINGLE_SEAT_OCCUPIED",
                            http_status=409,
                            detail=(
                                f"Single-seat role {norm_role} is already held by {incumbent.member_id}. "
                                "Explicit atomic_succession=True handoff is required."
                            ),
                        )
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                f"SINGLE_SEAT_OCCUPIED: Role {norm_role} permits strictly ONE active holder "
                                f"(current holder: {incumbent.member_id}). Use explicit atomic_succession handoff."
                            ),
                        )
                    # Atomic succession handoff inside the same transaction
                    incumbent.status = "SUPERSEDED"
                    incumbent.revoked_at_utc = now
                    incumbent.reason = reason.strip() or f"Atomic succession handoff to {clean_member}"
                    superseded_holder = self._serialize_role(incumbent)
                    get_active_hat_gateway().revoke_principal_sessions(incumbent.member_id)

            new_row = UserRoleAssignmentModel(
                assignment_id=f"ROLE-{uuid.uuid4().hex[:10].upper()}",
                member_id=clean_member,
                role_token=norm_role,
                house_id=resolved_house,
                status="ACTIVE",
                assigned_by=actor_id,
                assigned_at_utc=now,
                revoked_at_utc=None,
                reason=reason.strip() or f"Role {norm_role} granted by Chief Administrator",
            )
            db.add(new_row)

            # If member moved into Class T, they can hold zero custodial charges — reassign any active charges
            if is_class_t_role(norm_role):
                reassigned_charges = self._reassign_displaced_charges_in_tx(
                    db,
                    displaced_custodian_id=clean_member,
                    actor_id=actor_id,
                    now=now,
                    reason=f"Reassigned upon Class T technical role assignment ({norm_role})",
                )

            self._sync_member_role_mirrors(db, clean_member, norm_role)
            self._record_db_audit(
                db,
                tenant_id=f"HOUSE-{resolved_house:02d}" if resolved_house else "ENCLAVE",
                actor_id=actor_id,
                action="ROLE_SUCCESSION_HANDOFF" if superseded_holder else "ROLE_ASSIGNED",
                payload={
                    "assignment_id": new_row.assignment_id,
                    "member_id": clean_member,
                    "role_token": norm_role,
                    "house_id": resolved_house,
                    "superseded_holder": superseded_holder["member_id"] if superseded_holder else None,
                    "reassigned_charges_count": len(reassigned_charges),
                },
                recorded_at=now,
            )
            db.commit()
            db.refresh(new_row)
            serialized = self._serialize_role(new_row)

        audit_evt = get_governance_audit_log().record(
            event_type="ROLE_SUCCESSION_HANDOFF" if superseded_holder else "ROLE_ASSIGNED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=clean_member,
            action="ASSIGN_ROLE",
            outcome="SUCCESSION_COMPLETED" if superseded_holder else "ASSIGNED",
            http_status=201,
            detail=(
                f"Atomic succession for {norm_role}: {superseded_holder['member_id']} -> {clean_member}"
                if superseded_holder
                else f"Assigned role {norm_role} to {clean_member} (house={resolved_house or 'ENCLAVE'})."
            ),
            metadata={
                "assignment_id": serialized["assignment_id"],
                "role_token": norm_role,
                "superseded": superseded_holder,
            },
        )
        return {
            "status": "SUCCESSION_HANDOFF_COMPLETE" if superseded_holder else "ROLE_ASSIGNED",
            "assignment": serialized,
            "superseded_assignment": superseded_holder,
            "reassigned_charges": reassigned_charges,
            "audit_event_id": audit_evt["event_id"],
        }

    def revoke_role(
        self,
        *,
        member_id: str,
        role_token: str,
        reason: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = FOUNDER_MEMBER_ID,
    ) -> Dict[str, Any]:
        """Revoke an active role and atomically reassign any displaced custodial charges."""
        self._ensure_ready()
        clean_member = str(member_id or "").strip()
        norm_role = _validate_registry_role(role_token)

        if is_founder_target(clean_member) and (not is_chief_admin_role(actor_role) or norm_role == "CHIEF_ADMIN"):
            enforce_founder_immunity(
                target_id=clean_member,
                action="REVOKE_ROLE",
                actor_role=actor_role or "UNSPECIFIED",
                actor_id=actor_id,
            )

        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="REVOKE_ROLE",
            target_id=f"{clean_member}:{norm_role}",
        )

        now = _utc_now()
        with self._session_factory() as db:
            active_rows = (
                db.query(UserRoleAssignmentModel)
                .filter(
                    UserRoleAssignmentModel.member_id == clean_member,
                    UserRoleAssignmentModel.role_token == norm_role,
                    UserRoleAssignmentModel.status == "ACTIVE",
                )
                .all()
            )
            if not active_rows:
                raise HTTPException(
                    status_code=404,
                    detail=f"Active role assignment {norm_role} for {clean_member} not found.",
                )
            revoked_serialized = []
            for row in active_rows:
                row.status = "REVOKED"
                row.revoked_at_utc = now
                row.reason = reason.strip() or f"Revoked {norm_role} by Chief Administrator"
                revoked_serialized.append(self._serialize_role(row))

            # Check if member still holds any other custodial role
            remaining_active = (
                db.query(UserRoleAssignmentModel)
                .filter(
                    UserRoleAssignmentModel.member_id == clean_member,
                    UserRoleAssignmentModel.status == "ACTIVE",
                )
                .all()
            )
            remaining_roles = {r.role_token for r in remaining_active}
            if not remaining_roles:
                # Ensure baseline MEMBER_USER record exists
                db.add(
                    UserRoleAssignmentModel(
                        assignment_id=f"ROLE-{uuid.uuid4().hex[:10].upper()}",
                        member_id=clean_member,
                        role_token="MEMBER_USER",
                        house_id=active_rows[0].house_id,
                        status="ACTIVE",
                        assigned_by=actor_id,
                        assigned_at_utc=now,
                        reason="Default baseline membership after role revocation",
                    )
                )
                remaining_roles.add("MEMBER_USER")

            reassigned_charges: List[Dict[str, Any]] = []
            if not (remaining_roles & set(CUSTODIAL_MENTOR_ROLES)) and "CHIEF_ADMIN" not in remaining_roles:
                reassigned_charges = self._reassign_displaced_charges_in_tx(
                    db,
                    displaced_custodian_id=clean_member,
                    actor_id=actor_id,
                    now=now,
                    reason=f"Automatic custodial reassignment after revoking {norm_role} from {clean_member}",
                )

            get_active_hat_gateway().revoke_principal_sessions(clean_member)
            highest_remaining = max(remaining_roles, key=lambda r: ROLE_RANK.get(r, 0))
            self._sync_member_role_mirrors(db, clean_member, highest_remaining)
            self._record_db_audit(
                db,
                tenant_id="ENCLAVE",
                actor_id=actor_id,
                action="ROLE_REVOKED",
                payload={
                    "member_id": clean_member,
                    "revoked_role": norm_role,
                    "remaining_roles": sorted(remaining_roles),
                    "reassigned_charges": [c["charge_member_id"] for c in reassigned_charges],
                },
                recorded_at=now,
            )
            db.commit()

        audit_evt = get_governance_audit_log().record(
            event_type="ROLE_REVOKED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=clean_member,
            action="REVOKE_ROLE",
            outcome="REVOKED",
            http_status=200,
            detail=f"Revoked {norm_role} from {clean_member}; reassigned {len(reassigned_charges)} custodial charges.",
            metadata={"reassigned_charges": reassigned_charges},
        )
        return {
            "status": "ROLE_REVOKED",
            "member_id": clean_member,
            "revoked_assignments": revoked_serialized,
            "remaining_active_roles": sorted(remaining_roles),
            "reassigned_charges": reassigned_charges,
            "orphaned_charges_count": 0,
            "audit_event_id": audit_evt["event_id"],
        }

    def promote_member(
        self,
        *,
        member_id: str,
        to_role: str,
        house_id: Optional[int] = None,
        from_role: Optional[str] = None,
        atomic_succession: bool = False,
        reason: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = FOUNDER_MEMBER_ID,
    ) -> Dict[str, Any]:
        """Atomically promote a member to a higher authority tier with single-seat enforcement."""
        self._ensure_ready()
        clean_member = str(member_id or "").strip()
        if not clean_member:
            raise HTTPException(status_code=422, detail="member_id is required.")
        target_role = _validate_registry_role(to_role)
        resolved_house = _validate_house_id(house_id, required=False)

        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="PROMOTE_MEMBER",
            target_id=f"{clean_member}->{target_role}",
        )

        now = _utc_now()
        superseded_holder: Optional[Dict[str, Any]] = None
        reassigned_charges: List[Dict[str, Any]] = []

        with self._session_factory() as db:
            current_rows = (
                db.query(UserRoleAssignmentModel)
                .filter(
                    UserRoleAssignmentModel.member_id == clean_member,
                    UserRoleAssignmentModel.status == "ACTIVE",
                )
                .all()
            )
            current_roles = [r.role_token for r in current_rows]
            source_role = canonical_registry_role(from_role) if from_role else (
                max(current_roles, key=lambda r: ROLE_RANK.get(r, 0)) if current_roles else "MEMBER_USER"
            )
            if resolved_house is None and current_rows:
                resolved_house = next((r.house_id for r in current_rows if r.house_id is not None), None)

            if ROLE_RANK.get(target_role, 0) < ROLE_RANK.get(source_role, 0):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"INVALID_PROMOTION_DIRECTION: {source_role} -> {target_role} is a downgrade. "
                        "Use POST /api/v1/governance/roles/demote instead."
                    ),
                )

            # Single-seat check for CHIEF_ADMIN, T3, F3
            if target_role in SINGLE_SEAT_ROLES:
                incumbent = (
                    db.query(UserRoleAssignmentModel)
                    .filter(
                        UserRoleAssignmentModel.role_token == target_role,
                        UserRoleAssignmentModel.status == "ACTIVE",
                    )
                    .first()
                )
                if incumbent is not None and incumbent.member_id != clean_member:
                    if not atomic_succession:
                        get_governance_audit_log().record(
                            event_type="SINGLE_SEAT_CONFLICT",
                            actor_id=actor_id,
                            actor_role="CHIEF_ADMINISTRATOR",
                            target_id=f"{target_role}:{clean_member}",
                            action="PROMOTE_MEMBER",
                            outcome="CONFLICT_SINGLE_SEAT_OCCUPIED",
                            http_status=409,
                            detail=f"Cannot promote {clean_member} to occupied single-seat {target_role} without atomic_succession=True.",
                        )
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                f"SINGLE_SEAT_OCCUPIED: Seat {target_role} is currently occupied by "
                                f"{incumbent.member_id}. Supply atomic_succession=True to execute handoff."
                            ),
                        )
                    incumbent.status = "SUPERSEDED"
                    incumbent.revoked_at_utc = now
                    incumbent.reason = reason.strip() or f"Superseded by promotion of {clean_member} to {target_role}"
                    superseded_holder = self._serialize_role(incumbent)
                    get_active_hat_gateway().revoke_principal_sessions(incumbent.member_id)

            # Supersede previous lower role(s) if transitioning within hierarchy
            superseded_prior: List[Dict[str, Any]] = []
            for row in current_rows:
                if row.role_token == target_role:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Member {clean_member} already holds active role {target_role}.",
                    )
                if from_role and row.role_token != source_role:
                    continue
                if row.role_token == source_role or row.role_token == "MEMBER_USER":
                    row.status = "SUPERSEDED"
                    row.revoked_at_utc = now
                    row.reason = reason.strip() or f"Promoted from {row.role_token} to {target_role}"
                    superseded_prior.append(self._serialize_role(row))

            new_row = UserRoleAssignmentModel(
                assignment_id=f"ROLE-{uuid.uuid4().hex[:10].upper()}",
                member_id=clean_member,
                role_token=target_role,
                house_id=resolved_house,
                status="ACTIVE",
                assigned_by=actor_id,
                assigned_at_utc=now,
                revoked_at_utc=None,
                reason=reason.strip() or f"Promoted {source_role} -> {target_role}",
            )
            db.add(new_row)

            # Update custodian_role on active custodial charges, OR reassign if promoted to Class T / F3 (non-direct-custody)
            if is_class_t_role(target_role) or target_role == "F3":
                reassigned_charges = self._reassign_displaced_charges_in_tx(
                    db,
                    displaced_custodian_id=clean_member,
                    actor_id=actor_id,
                    now=now,
                    reason=f"Custodial charges reassigned upon promotion of {clean_member} to {target_role}",
                )
            else:
                active_charges = (
                    db.query(CustodialAssignmentModel)
                    .filter(
                        CustodialAssignmentModel.custodian_member_id == clean_member,
                        CustodialAssignmentModel.active == 1,
                    )
                    .all()
                )
                for ch in active_charges:
                    ch.custodian_role = target_role

            get_active_hat_gateway().revoke_principal_sessions(clean_member)
            self._sync_member_role_mirrors(db, clean_member, target_role)
            self._record_db_audit(
                db,
                tenant_id=f"HOUSE-{resolved_house:02d}" if resolved_house else "ENCLAVE",
                actor_id=actor_id,
                action="ROLE_PROMOTED",
                payload={
                    "member_id": clean_member,
                    "from_role": source_role,
                    "to_role": target_role,
                    "house_id": resolved_house,
                    "superseded_seat_holder": superseded_holder["member_id"] if superseded_holder else None,
                    "reassigned_charges": [c["charge_member_id"] for c in reassigned_charges],
                },
                recorded_at=now,
            )
            db.commit()
            db.refresh(new_row)
            serialized = self._serialize_role(new_row)

        audit_evt = get_governance_audit_log().record(
            event_type="ROLE_PROMOTED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=clean_member,
            action="PROMOTE_MEMBER",
            outcome="PROMOTED",
            http_status=200,
            detail=f"Promoted {clean_member}: {source_role} -> {target_role} (reassigned {len(reassigned_charges)} charges).",
            metadata={"from_role": source_role, "to_role": target_role, "reassigned_charges": reassigned_charges},
        )
        return {
            "status": "PROMOTED",
            "member_id": clean_member,
            "from_role": source_role,
            "to_role": target_role,
            "assignment": serialized,
            "superseded_seat_assignment": superseded_holder,
            "reassigned_charges": reassigned_charges,
            "orphaned_charges_count": 0,
            "audit_event_id": audit_evt["event_id"],
        }

    def demote_member(
        self,
        *,
        member_id: str,
        to_role: str = "MEMBER_USER",
        house_id: Optional[int] = None,
        from_role: Optional[str] = None,
        reason: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = FOUNDER_MEMBER_ID,
    ) -> Dict[str, Any]:
        """
        Atomically demote a member's tier, revoke displaced roles, and automatically
        reassign/escalate ALL displaced custodial charges in the same transaction.
        Guarantees zero orphaned accounts and zero lingering custodial access.
        """
        self._ensure_ready()
        clean_member = str(member_id or "").strip()
        if not clean_member:
            raise HTTPException(status_code=422, detail="member_id is required.")
        target_role = _validate_registry_role(to_role)
        resolved_house = _validate_house_id(house_id, required=False)

        # Founder Apex Immunity: NO tier (even Chief Admin via demote endpoint) may demote Founder root
        if is_founder_target(clean_member):
            enforce_founder_immunity(
                target_id=clean_member,
                action="DEMOTE_MEMBER",
                actor_role=actor_role or "UNSPECIFIED",
                actor_id=actor_id,
            )

        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="DEMOTE_MEMBER",
            target_id=f"{clean_member}->{target_role}",
        )

        now = _utc_now()
        with self._session_factory() as db:
            active_rows = (
                db.query(UserRoleAssignmentModel)
                .filter(
                    UserRoleAssignmentModel.member_id == clean_member,
                    UserRoleAssignmentModel.status == "ACTIVE",
                )
                .all()
            )
            if not active_rows:
                raise HTTPException(
                    status_code=404,
                    detail=f"No active role assignments found for member {clean_member}.",
                )

            current_highest = max((r.role_token for r in active_rows), key=lambda r: ROLE_RANK.get(r, 0))
            source_role = canonical_registry_role(from_role) if from_role else current_highest
            if resolved_house is None:
                resolved_house = next((r.house_id for r in active_rows if r.house_id is not None), None)

            if ROLE_RANK.get(target_role, 0) >= ROLE_RANK.get(source_role, 0):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"INVALID_DEMOTION_DIRECTION: {source_role} -> {target_role} is not a downgrade. "
                        "Use POST /api/v1/governance/roles/promote instead."
                    ),
                )

            revoked_roles: List[Dict[str, Any]] = []
            already_has_target = False
            for row in active_rows:
                if row.role_token == target_role:
                    already_has_target = True
                    continue
                if ROLE_RANK.get(row.role_token, 0) > ROLE_RANK.get(target_role, 0) or (
                    from_role and row.role_token == source_role
                ):
                    row.status = "REVOKED"
                    row.revoked_at_utc = now
                    row.reason = reason.strip() or f"Demoted from {row.role_token} to {target_role}"
                    revoked_roles.append(self._serialize_role(row))

            new_assignment_row: Optional[UserRoleAssignmentModel] = None
            if not already_has_target:
                new_assignment_row = UserRoleAssignmentModel(
                    assignment_id=f"ROLE-{uuid.uuid4().hex[:10].upper()}",
                    member_id=clean_member,
                    role_token=target_role,
                    house_id=resolved_house,
                    status="ACTIVE",
                    assigned_by=actor_id,
                    assigned_at_utc=now,
                    revoked_at_utc=None,
                    reason=reason.strip() or f"Demoted {source_role} -> {target_role}",
                )
                db.add(new_assignment_row)

            # Atomically reassign ALL displaced custodial charges in the SAME DB transaction
            reassigned_charges = self._reassign_displaced_charges_in_tx(
                db,
                displaced_custodian_id=clean_member,
                actor_id=actor_id,
                now=now,
                reason=reason.strip() or f"Atomic custodial reassignment upon demotion of {clean_member} ({source_role} -> {target_role})",
            )

            # Verify zero lingering active custodial charges remain for the demoted officer
            lingering_count = (
                db.query(CustodialAssignmentModel)
                .filter(
                    CustodialAssignmentModel.custodian_member_id == clean_member,
                    CustodialAssignmentModel.active == 1,
                )
                .count()
            )
            assert lingering_count == 0, "Invariant failure: lingering custodial charges after demotion"

            # Immediately invalidate any existing Active-Hat JWT session
            get_active_hat_gateway().revoke_principal_sessions(clean_member)
            self._sync_member_role_mirrors(db, clean_member, target_role)
            self._record_db_audit(
                db,
                tenant_id=f"HOUSE-{resolved_house:02d}" if resolved_house else "ENCLAVE",
                actor_id=actor_id,
                action="ROLE_DEMOTED",
                payload={
                    "member_id": clean_member,
                    "from_role": source_role,
                    "to_role": target_role,
                    "revoked_roles": [r["role_token"] for r in revoked_roles],
                    "reassigned_charges": [
                        {
                            "charge_member_id": c["charge_member_id"],
                            "new_custodian_member_id": c["custodian_member_id"],
                            "new_custodian_role": c["custodian_role"],
                            "assignment_mode": c["assignment_mode"],
                        }
                        for c in reassigned_charges
                    ],
                },
                recorded_at=now,
            )
            db.commit()
            if new_assignment_row is not None:
                db.refresh(new_assignment_row)
            serialized_new = (
                self._serialize_role(new_assignment_row)
                if new_assignment_row is not None
                else self._serialize_role(
                    db.query(UserRoleAssignmentModel)
                    .filter(
                        UserRoleAssignmentModel.member_id == clean_member,
                        UserRoleAssignmentModel.role_token == target_role,
                        UserRoleAssignmentModel.status == "ACTIVE",
                    )
                    .first()
                )
            )

        audit_evt = get_governance_audit_log().record(
            event_type="ROLE_DEMOTED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=clean_member,
            action="DEMOTE_MEMBER",
            outcome="DEMOTED_AND_CHARGES_REASSIGNED",
            http_status=200,
            detail=(
                f"Demoted {clean_member}: {source_role} -> {target_role}. "
                f"Atomically reassigned {len(reassigned_charges)} custodial charge(s); 0 orphaned, 0 lingering."
            ),
            metadata={"from_role": source_role, "to_role": target_role, "reassigned_charges": reassigned_charges},
        )
        return {
            "status": "DEMOTED",
            "member_id": clean_member,
            "from_role": source_role,
            "to_role": target_role,
            "assignment": serialized_new,
            "revoked_assignments": revoked_roles,
            "reassigned_charges": reassigned_charges,
            "orphaned_charges_count": 0,
            "lingering_custodial_access_count": 0,
            "audit_event_id": audit_evt["event_id"],
        }

    def _sync_member_role_mirrors(self, db: Session, member_id: str, new_role: str) -> None:
        user = db.get(UserModel, member_id)
        if user is not None:
            user.role = new_role
        onb = db.get(OnboardingMemberModel, member_id)
        if onb is not None:
            onb.role_tier = new_role

    # ------------------------------------------------------------------
    # 3. Anti-Tribalism Custody Mode & Custodial Assignment Engine
    # ------------------------------------------------------------------

    def get_policy_controls(self) -> Dict[str, Any]:
        self._ensure_ready()
        with self._session_factory() as db:
            row = db.get(EnclavePolicyControlModel, "GLOBAL")
            if row is None:
                self._seed_defaults(db)
                row = db.get(EnclavePolicyControlModel, "GLOBAL")
            return self._serialize_policy(row)

    def set_custody_assignment_mode(
        self,
        *,
        custody_assignment_mode: str,
        reason: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = FOUNDER_MEMBER_ID,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="SET_CUSTODY_ASSIGNMENT_MODE",
            target_id=str(custody_assignment_mode),
        )
        mode_norm = str(custody_assignment_mode or "").strip().upper()
        if mode_norm not in VALID_CUSTODY_MODES:
            raise HTTPException(
                status_code=422,
                detail=f"custody_assignment_mode must be one of {', '.join(VALID_CUSTODY_MODES)}.",
            )
        now = _utc_now()
        with self._session_factory() as db:
            row = db.get(EnclavePolicyControlModel, "GLOBAL")
            previous = row.custody_assignment_mode if row else CUSTODY_MODE_INTRA_HOUSE
            row.custody_assignment_mode = mode_norm
            row.updated_by = actor_id
            row.updated_at_utc = now
            row.reason = reason.strip() or f"Custody mode switched to {mode_norm}"
            self._record_db_audit(
                db,
                tenant_id="ENCLAVE",
                actor_id=actor_id,
                action="CUSTODY_MODE_CHANGED",
                payload={"previous_mode": previous, "new_mode": mode_norm, "reason": row.reason},
                recorded_at=now,
            )
            db.commit()
            db.refresh(row)
            serialized = self._serialize_policy(row)

        audit_evt = get_governance_audit_log().record(
            event_type="CUSTODY_MODE_CHANGED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=mode_norm,
            action="SET_CUSTODY_ASSIGNMENT_MODE",
            outcome=f"{previous}->{mode_norm}",
            http_status=200,
            detail=f"Enclave custody assignment mode transitioned {previous} -> {mode_norm}.",
        )
        return {**serialized, "previous_mode": previous, "audit_event_id": audit_evt["event_id"]}

    def _select_eligible_custodian_in_tx(
        self,
        db: Session,
        *,
        charge_house_id: int,
        exclude_member_ids: Set[str],
        mode: str,
    ) -> Tuple[str, str, Optional[int]]:
        """
        Select an eligible active custodian honoring INTRA_HOUSE vs CROSS_HOUSE_ANTI_TRIBAL.
        Always falls back to Chief Admin (FOUNDER_MEMBER_ID) so zero accounts can ever be orphaned.
        """
        active_officers = (
            db.query(UserRoleAssignmentModel)
            .filter(
                UserRoleAssignmentModel.status == "ACTIVE",
                UserRoleAssignmentModel.role_token.in_(CUSTODIAL_MENTOR_ROLES),
            )
            .order_by(UserRoleAssignmentModel.assigned_at_utc.asc())
            .all()
        )
        candidates = [o for o in active_officers if o.member_id not in exclude_member_ids]

        if mode == CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL:
            # Prefer F1 / F2-A mentors from a DIFFERENT House to prevent favoritism and tribalism
            for role_group in (("F1", "F2-A"), ("F2-H", "H2")):
                cross_house = [
                    o
                    for o in candidates
                    if o.role_token in role_group and o.house_id is not None and int(o.house_id) != int(charge_house_id)
                ]
                if cross_house:
                    chosen = cross_house[0]
                    return chosen.member_id, chosen.role_token, chosen.house_id
            # Escalate to Chief Admin custodial queue if no cross-house mentor is available
            return FOUNDER_MEMBER_ID, "CHIEF_ADMIN", 1

        # INTRA_HOUSE default: prefer mentor/custodian inside the SAME House
        for role_group in (("F1", "F2-A"), ("F2-H", "H2")):
            same_house = [
                o
                for o in candidates
                if o.role_token in role_group and o.house_id is not None and int(o.house_id) == int(charge_house_id)
            ]
            if same_house:
                chosen = same_house[0]
                return chosen.member_id, chosen.role_token, chosen.house_id

        # Fallback: any active custodial officer, then Chief Admin queue
        if candidates:
            chosen = candidates[0]
            return chosen.member_id, chosen.role_token, chosen.house_id
        return FOUNDER_MEMBER_ID, "CHIEF_ADMIN", 1

    def _reassign_displaced_charges_in_tx(
        self,
        db: Session,
        *,
        displaced_custodian_id: str,
        actor_id: str,
        now: str,
        reason: str,
    ) -> List[Dict[str, Any]]:
        policy = db.get(EnclavePolicyControlModel, "GLOBAL")
        active_mode = policy.custody_assignment_mode if policy else CUSTODY_MODE_INTRA_HOUSE

        displaced_rows = (
            db.query(CustodialAssignmentModel)
            .filter(
                CustodialAssignmentModel.custodian_member_id == displaced_custodian_id,
                CustodialAssignmentModel.active == 1,
            )
            .all()
        )
        reassigned: List[Dict[str, Any]] = []
        for old in displaced_rows:
            old.active = 0
            old.ended_at_utc = now
            old.reason = reason

            new_cust_id, new_cust_role, _ = self._select_eligible_custodian_in_tx(
                db,
                charge_house_id=int(old.charge_house_id),
                exclude_member_ids={displaced_custodian_id, old.charge_member_id},
                mode=active_mode,
            )
            new_row = CustodialAssignmentModel(
                custody_id=f"CUST-{uuid.uuid4().hex[:10].upper()}",
                custodian_member_id=new_cust_id,
                custodian_role=new_cust_role,
                charge_member_id=old.charge_member_id,
                charge_scma_id=old.charge_scma_id,
                charge_house_id=int(old.charge_house_id),
                assignment_mode=active_mode,
                active=1,
                assigned_by=actor_id,
                assigned_at_utc=now,
                ended_at_utc=None,
                reason=reason,
            )
            db.add(new_row)
            db.flush()
            reassigned.append(self._serialize_custody(new_row))
        return reassigned

    def assign_custodian(
        self,
        *,
        charge_member_id: str,
        charge_scma_id: str,
        charge_house_id: int,
        custodian_member_id: Optional[str] = None,
        custodian_role: Optional[str] = None,
        reason: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = FOUNDER_MEMBER_ID,
    ) -> Dict[str, Any]:
        """Assign or re-pair a custodial officer to a charge honoring active custody_assignment_mode."""
        self._ensure_ready()
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="ASSIGN_CUSTODIAN",
            target_id=charge_member_id,
        )
        resolved_house = _validate_house_id(charge_house_id, required=True)
        now = _utc_now()
        with self._session_factory() as db:
            policy = db.get(EnclavePolicyControlModel, "GLOBAL")
            active_mode = policy.custody_assignment_mode if policy else CUSTODY_MODE_INTRA_HOUSE

            if custodian_member_id:
                clean_cust = custodian_member_id.strip()
                cust_role_row = (
                    db.query(UserRoleAssignmentModel)
                    .filter(
                        UserRoleAssignmentModel.member_id == clean_cust,
                        UserRoleAssignmentModel.status == "ACTIVE",
                    )
                    .order_by(UserRoleAssignmentModel.assigned_at_utc.desc())
                    .first()
                )
                resolved_cust_role = (
                    canonical_registry_role(custodian_role)
                    if custodian_role
                    else (cust_role_row.role_token if cust_role_row else "F1")
                )
                if is_class_t_role(resolved_cust_role):
                    raise HTTPException(
                        status_code=403,
                        detail="CLASS_T_BOUNDARY_VIOLATION: Class T technical roles cannot hold custodial assignments.",
                    )
                if (
                    active_mode == CUSTODY_MODE_CROSS_HOUSE_ANTI_TRIBAL
                    and resolved_cust_role in {"F1", "F2-A"}
                    and cust_role_row is not None
                    and cust_role_row.house_id is not None
                    and int(cust_role_row.house_id) == int(resolved_house)
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"ANTI_TRIBALISM_CUSTODY_VIOLATION: Enclave is in CROSS_HOUSE_ANTI_TRIBAL mode; "
                            f"{resolved_cust_role} mentor {clean_cust} from HOUSE-{int(resolved_house):02d} cannot be paired intra-house."
                        ),
                    )
                chosen_id, chosen_role = clean_cust, resolved_cust_role
            else:
                chosen_id, chosen_role, _ = self._select_eligible_custodian_in_tx(
                    db,
                    charge_house_id=int(resolved_house),
                    exclude_member_ids={charge_member_id.strip()},
                    mode=active_mode,
                )

            # Deactivate existing active assignment(s) for this charge
            prior_rows = (
                db.query(CustodialAssignmentModel)
                .filter(
                    CustodialAssignmentModel.charge_member_id == charge_member_id.strip(),
                    CustodialAssignmentModel.active == 1,
                )
                .all()
            )
            for p in prior_rows:
                p.active = 0
                p.ended_at_utc = now

            new_row = CustodialAssignmentModel(
                custody_id=f"CUST-{uuid.uuid4().hex[:10].upper()}",
                custodian_member_id=chosen_id,
                custodian_role=chosen_role,
                charge_member_id=charge_member_id.strip(),
                charge_scma_id=charge_scma_id.strip(),
                charge_house_id=int(resolved_house),
                assignment_mode=active_mode,
                active=1,
                assigned_by=actor_id,
                assigned_at_utc=now,
                ended_at_utc=None,
                reason=reason.strip() or f"Assigned under {active_mode} policy",
            )
            db.add(new_row)
            db.commit()
            db.refresh(new_row)
            serialized = self._serialize_custody(new_row)

        audit_evt = get_governance_audit_log().record(
            event_type="CUSTODIAL_ASSIGNMENT_CREATED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=charge_member_id,
            action="ASSIGN_CUSTODIAN",
            outcome="ASSIGNED",
            http_status=201,
            detail=f"Assigned custodian {chosen_id} ({chosen_role}) to {charge_member_id} under {active_mode}.",
        )
        return {"status": "CUSTODIAN_ASSIGNED", "assignment": serialized, "audit_event_id": audit_evt["event_id"]}

    def list_custodial_assignments(
        self,
        *,
        custodian_member_id: Optional[str] = None,
        charge_member_id: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        self._ensure_ready()
        with self._session_factory() as db:
            q = db.query(CustodialAssignmentModel)
            if active_only:
                q = q.filter(CustodialAssignmentModel.active == 1)
            if custodian_member_id:
                q = q.filter(CustodialAssignmentModel.custodian_member_id == custodian_member_id.strip())
            if charge_member_id:
                q = q.filter(CustodialAssignmentModel.charge_member_id == charge_member_id.strip())
            rows = q.order_by(CustodialAssignmentModel.assigned_at_utc.desc()).all()
            return [self._serialize_custody(r) for r in rows]

    # ------------------------------------------------------------------
    # 4. Scoped Family Member / Account Lookup Engine
    # ------------------------------------------------------------------

    def _build_unified_directory(self, db: Session) -> List[Dict[str, Any]]:
        """Assemble unified member records from relational tables and runtime lineage."""
        by_member_id: Dict[str, Dict[str, Any]] = {}
        scma_to_member: Dict[str, str] = {}

        # 1. Runtime lineage houses (canonical baseline + synced dynamic members)
        for house in self._lineage.list_all_houses():
            hid = int(house["house_id"])
            lcode = house["lineage_code"]
            for m in house["members"]:
                scma_id = str(m["scma_id"])
                mid = str(m.get("member_id") or f"USR-{scma_id}")
                # Map canonical seeded Vance IDs
                if scma_id == "SCMA-FOUNDER_-C8575D7E":
                    mid = FOUNDER_MEMBER_ID
                elif scma_id == "SCMA-ELEANOR_-B2B31C9E":
                    mid = "USR-eleanor_va-B2B31C9E"
                elif scma_id == "SCMA-JULIAN_-A1F98B21":
                    mid = "USR-julian_va-A1F98B21"
                scma_to_member[scma_id] = mid
                by_member_id[mid] = {
                    "member_id": mid,
                    "scma_id": scma_id,
                    "full_name": str(m.get("name", scma_id)),
                    "house_id": hid,
                    "lineage_code": lcode,
                    "role_tier": str(m.get("role_tier") or m.get("role_tag") or "MEMBER_USER"),
                    "balance_cents": int(m.get("cash_cents", 0)),
                    "high_water_mark_cents": int(m.get("high_water_mark_cents", m.get("cash_cents", 0))),
                    "risk_dial_bps": int(round(float(m.get("risk_dial", 0.01)) * 10_000)),
                    "is_custodial": bool(m.get("is_custodial", False)),
                    "status": str(m.get("status", "ACTIVE")),
                    "household_id": "HOUSEHOLD-ALPHA" if hid in (1, 2) else f"HOUSEHOLD-H{hid:02d}",
                }

        # 2. Relational LineageHouseMemberModel
        for row in db.query(LineageHouseMemberModel).all():
            mid = row.member_id or scma_to_member.get(row.scma_id) or f"USR-{row.scma_id}"
            scma_to_member[row.scma_id] = mid
            rec = by_member_id.get(mid, {})
            rec.update(
                {
                    "member_id": mid,
                    "scma_id": row.scma_id,
                    "full_name": row.name,
                    "house_id": int(row.house_id),
                    "lineage_code": f"HOUSE-{int(row.house_id):02d}",
                    "role_tier": rec.get("role_tier") or row.role_tag,
                    "balance_cents": int(row.cash_cents),
                    "high_water_mark_cents": int(row.high_water_mark_cents),
                    "risk_dial_bps": int(row.risk_dial_bps),
                    "is_custodial": bool(row.is_custodial),
                    "status": row.status,
                    "household_id": rec.get("household_id") or ("HOUSEHOLD-ALPHA" if int(row.house_id) in (1, 2) else f"HOUSEHOLD-H{int(row.house_id):02d}"),
                }
            )
            by_member_id[mid] = rec

        # 3. Persistent OnboardingMemberModel (authoritative for onboarded/ratified members)
        for row in db.query(OnboardingMemberModel).all():
            scma_to_member[row.scma_id] = row.member_id
            by_member_id[row.member_id] = {
                "member_id": row.member_id,
                "scma_id": row.scma_id,
                "full_name": row.full_name,
                "house_id": int(row.house_id),
                "lineage_code": row.lineage_code,
                "role_tier": row.role_tier,
                "balance_cents": int(row.seed_cents),
                "high_water_mark_cents": int(row.high_water_mark_cents),
                "risk_dial_bps": int(row.risk_dial_bps),
                "is_custodial": bool(row.is_custodial),
                "status": row.status,
                "bank_ref_token": row.bank_ref_token,
                "household_id": f"HOUSEHOLD-H{int(row.house_id):02d}",
            }

        # 4. Enrich with active relational roles and custodial assignments
        role_map: Dict[str, List[str]] = {}
        for ra in db.query(UserRoleAssignmentModel).filter(UserRoleAssignmentModel.status == "ACTIVE").all():
            role_map.setdefault(ra.member_id, []).append(ra.role_token)

        custodian_map: Dict[str, Dict[str, Any]] = {}
        for ca in db.query(CustodialAssignmentModel).filter(CustodialAssignmentModel.active == 1).all():
            custodian_map[ca.charge_member_id] = {
                "custody_id": ca.custody_id,
                "custodian_member_id": ca.custodian_member_id,
                "custodian_role": ca.custodian_role,
                "assignment_mode": ca.assignment_mode,
            }
            if ca.charge_member_id not in by_member_id:
                by_member_id[ca.charge_member_id] = {
                    "member_id": ca.charge_member_id,
                    "scma_id": ca.charge_scma_id,
                    "full_name": ca.charge_member_id,
                    "house_id": int(ca.charge_house_id),
                    "lineage_code": f"HOUSE-{int(ca.charge_house_id):02d}",
                    "role_tier": "MEMBER_USER",
                    "balance_cents": 0,
                    "high_water_mark_cents": 0,
                    "risk_dial_bps": 100,
                    "is_custodial": True,
                    "status": "ACTIVE",
                    "household_id": f"HOUSEHOLD-H{int(ca.charge_house_id):02d}",
                }

        results: List[Dict[str, Any]] = []
        for mid, rec in by_member_id.items():
            rec["active_roles"] = sorted(set(role_map.get(mid, []))) or [canonical_registry_role(rec.get("role_tier")) or "MEMBER_USER"]
            rec["custodial_assignment"] = custodian_map.get(mid)
            results.append(rec)
        results.sort(key=lambda r: (int(r["house_id"]), r["full_name"]))
        return results

    def _resolve_lookup_authority(
        self,
        db: Session,
        *,
        actor_role: Optional[str],
        actor_id: Optional[str],
        house_id: Optional[int],
        household_id: Optional[str],
    ) -> Dict[str, Any]:
        """Resolve effective server-side lookup authority, validating live DB role assignments."""
        clean_actor_id = (actor_id or "").strip()
        claimed_role = canonical_registry_role(actor_role)

        # If caller identifies a concrete member_id present in user_role_assignments, DB is authoritative!
        db_active_rows: List[UserRoleAssignmentModel] = []
        has_any_db_rows = False
        if clean_actor_id:
            all_rows = (
                db.query(UserRoleAssignmentModel)
                .filter(UserRoleAssignmentModel.member_id == clean_actor_id)
                .all()
            )
            has_any_db_rows = len(all_rows) > 0
            db_active_rows = [r for r in all_rows if r.status == "ACTIVE"]

        if has_any_db_rows:
            active_role_set = {r.role_token for r in db_active_rows}
            # If caller explicitly claims a role they no longer hold (e.g., after demotion/revocation), fail closed!
            if claimed_role and claimed_role not in active_role_set and "CHIEF_ADMIN" not in active_role_set:
                get_governance_audit_log().record(
                    event_type="CUSTODIAL_LOOKUP_DENIED",
                    actor_id=clean_actor_id,
                    actor_role=claimed_role,
                    target_id="CUSTODIAL_LOOKUP",
                    action="CUSTODIAL_LOOKUP",
                    outcome="DENIED_ROLE_REVOKED_OR_DEMOTED",
                    http_status=403,
                    detail=f"Actor {clean_actor_id} no longer holds active role {claimed_role}; active roles: {sorted(active_role_set)}.",
                )
                raise HTTPException(
                    status_code=403,
                    detail=f"CUSTODIAL_ACCESS_REVOKED: Actor {clean_actor_id} does not hold active role {claimed_role}.",
                )
            eff_role = claimed_role if (claimed_role and claimed_role in active_role_set) else (
                max(active_role_set, key=lambda r: ROLE_RANK.get(r, 0)) if active_role_set else "MEMBER_USER"
            )
            assigned_houses = {int(r.house_id) for r in db_active_rows if r.house_id is not None}
            if house_id is not None and eff_role not in {"CHIEF_ADMIN", "CHIEF_ADMIN_DEPUTY", "F3"} and not is_class_t_role(eff_role):
                if assigned_houses and int(house_id) not in assigned_houses:
                    raise HTTPException(
                        status_code=403,
                        detail=f"CROSS_HOUSE_LOOKUP_FORBIDDEN: Actor {clean_actor_id} is not assigned to HOUSE-{int(house_id):02d}.",
                    )
            direct_charges = {
                c.charge_member_id
                for c in db.query(CustodialAssignmentModel)
                .filter(
                    CustodialAssignmentModel.custodian_member_id == clean_actor_id,
                    CustodialAssignmentModel.active == 1,
                )
                .all()
            }
            return {
                "actor_id": clean_actor_id,
                "effective_role": eff_role,
                "assigned_houses": assigned_houses,
                "direct_charge_ids": direct_charges,
                "has_db_identity": True,
                "household_id": household_id,
            }

        # Portal session without explicit DB member_id (e.g., UI desk query with role + house/household)
        eff_role = claimed_role or "MEMBER_USER"
        assigned_houses: Set[int] = set()
        if house_id is not None:
            assigned_houses.add(int(house_id))
        elif household_id:
            hh = household_id.strip().upper()
            if hh == "HOUSEHOLD-ALPHA":
                assigned_houses.update({1, 2})
            elif hh == "HOUSEHOLD-BETA":
                assigned_houses.add(2)
        direct_charges_set: Set[str] = set()
        if clean_actor_id:
            direct_charges_set = {
                c.charge_member_id
                for c in db.query(CustodialAssignmentModel)
                .filter(
                    CustodialAssignmentModel.custodian_member_id == clean_actor_id,
                    CustodialAssignmentModel.active == 1,
                )
                .all()
            }
        return {
            "actor_id": clean_actor_id or eff_role,
            "effective_role": eff_role,
            "assigned_houses": assigned_houses,
            "direct_charge_ids": direct_charges_set,
            "has_db_identity": False,
            "household_id": household_id,
        }

    def _is_member_in_scope(self, member: Dict[str, Any], auth: Dict[str, Any]) -> bool:
        role = auth["effective_role"]
        if role in {"CHIEF_ADMIN", "CHIEF_ADMIN_DEPUTY", "F3"}:
            return True
        if is_class_t_role(role):
            return True  # Class T gets strictly R-12 masked node/relay telemetry only
        if role == "MEMBER_USER":
            return False

        mid = member["member_id"]
        m_house = int(member["house_id"])
        direct_charges: Set[str] = auth["direct_charge_ids"]
        assigned_houses: Set[int] = auth["assigned_houses"]

        if role == "F1":
            # F1 mentor is strictly limited to direct custodial charges
            if auth["has_db_identity"] or direct_charges:
                return mid in direct_charges
            # Demo fallback when no concrete DB actor_id passed: custodial apprentices in assigned household
            return bool(member.get("is_custodial")) and (not assigned_houses or m_house in assigned_houses)

        if role in {"F2-H", "F2-A"}:
            if mid in direct_charges:
                return True
            if assigned_houses:
                return m_house in assigned_houses
            # If concrete DB officer has neither assigned house nor direct charges, fail closed
            if auth["has_db_identity"]:
                return False
            return m_house in {1, 2}

        if role in {"H1", "H2", "HOUSE_GENEALOGIST"}:
            if mid in direct_charges:
                return True
            if assigned_houses:
                return m_house in assigned_houses
            return False

        return False

    def _project_lookup_record(self, member: Dict[str, Any], role: str) -> Dict[str, Any]:
        """Project a member record strictly according to caller's role & Directive R-12 masking."""
        if is_class_t_role(role):
            hid = int(member["house_id"])
            relay_id = f"RELAY-HOUSE-{hid:02d}-{hashlib.sha256(member['scma_id'].encode()).hexdigest()[:6].upper()}"
            return {
                "lookup_type": "TECHNICAL_NODE_RELAY",
                "relay_node_id": relay_id,
                "member_id": "MEM-REDACTED",
                "full_name": f"Node Relay {relay_id}",
                "scma_id": "SCMA-MEM-****",
                "house_id": hid,
                "lineage_code": member["lineage_code"],
                "balance_cents": "$****.**",
                "balance_display": "$****.**",
                "high_water_mark_cents": "$****.**",
                "worker_status": "NOMINAL" if member["status"] == "ACTIVE" else member["status"],
                "latency_ms": 12 + (hid % 7),
                "r12_masked": True,
                "directive_enforced": "Directive R-12 (Least Privilege Redacted Telemetry)",
            }

        if role == "F3":
            return {
                "lookup_type": "MACRO_RISK_PROFILE",
                "member_id": member["member_id"],
                "scma_id": member["scma_id"],
                "full_name": member["full_name"],
                "house_id": int(member["house_id"]),
                "lineage_code": member["lineage_code"],
                "role_tier": member["role_tier"],
                "active_roles": member["active_roles"],
                "risk_dial_bps": int(member["risk_dial_bps"]),
                "risk_dial_pct": round(int(member["risk_dial_bps"]) / 100.0, 2),
                "status": member["status"],
                "is_custodial": bool(member["is_custodial"]),
                "custodial_assignment": member.get("custodial_assignment"),
                "macro_exposure_cents": int(member["balance_cents"]),
                "macro_exposure_display": format_cents(int(member["balance_cents"])),
                "r12_masked": False,
                "scope": "ENCLAVE_WIDE_MACRO_RISK",
            }

        r12_masked = role in {"F1", "H1"}
        bal_cents = int(member["balance_cents"])
        hwm_cents = int(member["high_water_mark_cents"])
        return {
            "lookup_type": "CUSTODIAL_MEMBER_ACCOUNT",
            "member_id": member["member_id"],
            "scma_id": member["scma_id"],
            "full_name": member["full_name"],
            "house_id": int(member["house_id"]),
            "lineage_code": member["lineage_code"],
            "role_tier": member["role_tier"],
            "active_roles": member["active_roles"],
            "balance_cents": "$****.**" if r12_masked else bal_cents,
            "balance_display": "$****.**" if r12_masked else format_cents(bal_cents),
            "high_water_mark_cents": "$****.**" if r12_masked else hwm_cents,
            "risk_dial_bps": int(member["risk_dial_bps"]),
            "risk_dial_pct": round(int(member["risk_dial_bps"]) / 100.0, 2),
            "is_custodial": bool(member["is_custodial"]),
            "custodial_assignment": member.get("custodial_assignment"),
            "status": member["status"],
            "r12_masked": r12_masked,
            "scope": "ENCLAVE_WIDE" if role == "CHIEF_ADMIN" else f"SCOPED_{role}",
        }

    def custodial_lookup(
        self,
        *,
        q: str = "",
        actor_role: Optional[str] = None,
        actor_id: Optional[str] = None,
        house_id: Optional[int] = None,
        household_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        needle = (q or "").strip().lower()
        with self._session_factory() as db:
            auth = self._resolve_lookup_authority(
                db,
                actor_role=actor_role,
                actor_id=actor_id,
                house_id=house_id,
                household_id=household_id,
            )
            eff_role = auth["effective_role"]
            if eff_role == "MEMBER_USER":
                get_governance_audit_log().record(
                    event_type="CUSTODIAL_LOOKUP_DENIED",
                    actor_id=auth["actor_id"],
                    actor_role="MEMBER_USER",
                    target_id="CUSTODIAL_LOOKUP",
                    action="CUSTODIAL_LOOKUP",
                    outcome="DENIED_NO_CUSTODIAL_AUTHORITY",
                    http_status=403,
                    detail="Standard members have zero custodial lookup privileges.",
                )
                raise HTTPException(
                    status_code=403,
                    detail="CUSTODIAL_LOOKUP_FORBIDDEN: Custodial lookup requires an active officer role.",
                )

            directory = self._build_unified_directory(db)
            scoped = [m for m in directory if self._is_member_in_scope(m, auth)]

            matched: List[Dict[str, Any]] = []
            for m in scoped:
                projected = self._project_lookup_record(m, eff_role)
                if needle:
                    if is_class_t_role(eff_role):
                        # Class T searches strictly against technical node/relay metadata & House code
                        haystack = " ".join(
                            [
                                str(projected.get("relay_node_id", "")),
                                str(projected.get("lineage_code", "")),
                                str(projected.get("worker_status", "")),
                                "scma-mem-****",
                                f"house-{m['house_id']:02d}",
                                f"house {m['house_id']}",
                            ]
                        ).lower()
                    else:
                        haystack = " ".join(
                            [
                                str(m["member_id"]),
                                str(m["scma_id"]),
                                str(m["full_name"]),
                                str(m["lineage_code"]),
                                str(m["role_tier"]),
                                " ".join(m.get("active_roles", [])),
                            ]
                        ).lower()
                    if needle not in haystack:
                        continue
                matched.append(projected)

            return {
                "query": q,
                "actor_id": auth["actor_id"],
                "effective_role": eff_role,
                "read_only": eff_role == "CHIEF_ADMIN_DEPUTY",
                "scope": (
                    "TECHNICAL_NODE_RELAY_R12_MASKED"
                    if is_class_t_role(eff_role)
                    else (
                        "ENCLAVE_WIDE_READ_ONLY"
                        if eff_role == "CHIEF_ADMIN_DEPUTY"
                        else ("ENCLAVE_WIDE" if eff_role in {"CHIEF_ADMIN", "F3"} else "SCOPED_CUSTODIAL")
                    )
                ),
                "r12_masked": is_class_t_role(eff_role) or eff_role in {"F1", "H1"},
                "count": len(matched),
                "results": matched,
            }

    def custodial_member_detail(
        self,
        *,
        target_member_id: str,
        actor_role: Optional[str] = None,
        actor_id: Optional[str] = None,
        house_id: Optional[int] = None,
        household_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        clean_target = (target_member_id or "").strip()
        with self._session_factory() as db:
            auth = self._resolve_lookup_authority(
                db,
                actor_role=actor_role,
                actor_id=actor_id,
                house_id=house_id,
                household_id=household_id,
            )
            eff_role = auth["effective_role"]
            if eff_role == "MEMBER_USER":
                get_governance_audit_log().record(
                    event_type="CUSTODIAL_LOOKUP_DENIED",
                    actor_id=auth["actor_id"],
                    actor_role="MEMBER_USER",
                    target_id=clean_target,
                    action="CUSTODIAL_MEMBER_DETAIL",
                    outcome="DENIED_NO_CUSTODIAL_AUTHORITY",
                    http_status=403,
                    detail=f"Blocked MEMBER_USER attempt to inspect {clean_target}.",
                )
                raise HTTPException(
                    status_code=403,
                    detail="CUSTODIAL_LOOKUP_FORBIDDEN: Member lacks custodial inspection authority.",
                )

            directory = self._build_unified_directory(db)
            target = next(
                (m for m in directory if m["member_id"] == clean_target or m["scma_id"] == clean_target),
                None,
            )
            if target is None:
                # If Class T queries by relay_node_id, match deterministically
                if is_class_t_role(eff_role):
                    for m in directory:
                        proj = self._project_lookup_record(m, eff_role)
                        if proj["relay_node_id"] == clean_target:
                            return {"member": proj, "r12_masked": True, "effective_role": eff_role}
                raise HTTPException(status_code=404, detail=f"Member '{clean_target}' not found.")

            if not self._is_member_in_scope(target, auth):
                get_governance_audit_log().record(
                    event_type="CUSTODIAL_LOOKUP_DENIED",
                    actor_id=auth["actor_id"],
                    actor_role=eff_role,
                    target_id=clean_target,
                    action="CUSTODIAL_MEMBER_DETAIL",
                    outcome="DENIED_OUT_OF_SCOPE",
                    http_status=403,
                    detail=f"Blocked out-of-scope custodial lookup of {clean_target} by {auth['actor_id']} ({eff_role}).",
                )
                raise HTTPException(
                    status_code=403,
                    detail=f"OUT_OF_SCOPE_CUSTODIAL_LOOKUP: {auth['actor_id']} ({eff_role}) is not authorized to view {clean_target}.",
                )

            projected = self._project_lookup_record(target, eff_role)
            return {
                "effective_role": eff_role,
                "r12_masked": projected["r12_masked"],
                "member": projected,
            }

    # ------------------------------------------------------------------
    # 5. 3-Stage Delegated Onboarding & Genealogical Ratification
    # ------------------------------------------------------------------

    def update_delegation_config(
        self,
        *,
        delegated_onboarding_scope: Optional[str] = None,
        admission_authority_mode: Optional[str] = None,
        house_delegation_flags: Optional[Dict[Any, Any]] = None,
        genealogical_board_enabled: Optional[bool] = None,
        genealogical_board_quorum: Optional[int] = None,
        reason: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = FOUNDER_MEMBER_ID,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="UPDATE_DELEGATION_CONFIG",
            target_id="DELEGATED_ONBOARDING_CONFIG",
        )
        now = _utc_now()
        with self._session_factory() as db:
            row = db.get(EnclavePolicyControlModel, "GLOBAL")
            if delegated_onboarding_scope is not None:
                scope_norm = str(delegated_onboarding_scope).strip().upper()
                if scope_norm not in VALID_DELEGATION_SCOPES:
                    raise HTTPException(
                        status_code=422,
                        detail=f"delegated_onboarding_scope must be one of {', '.join(VALID_DELEGATION_SCOPES)}.",
                    )
                row.delegated_onboarding_scope = scope_norm
            if admission_authority_mode is not None:
                mode_norm = str(admission_authority_mode).strip().upper()
                if mode_norm not in VALID_ADMISSION_AUTHORITY_MODES:
                    raise HTTPException(
                        status_code=422,
                        detail=f"admission_authority_mode must be one of {', '.join(VALID_ADMISSION_AUTHORITY_MODES)}.",
                    )
                row.admission_authority_mode = mode_norm
            if house_delegation_flags is not None:
                try:
                    current_flags = json.loads(row.house_delegation_flags_json or "{}")
                except Exception:
                    current_flags = {}
                for k, v in house_delegation_flags.items():
                    hid = _validate_house_id(k, required=True)
                    current_flags[str(hid)] = bool(v)
                row.house_delegation_flags_json = json.dumps(current_flags)
            if genealogical_board_enabled is not None:
                row.genealogical_board_enabled = 1 if genealogical_board_enabled else 0
            if genealogical_board_quorum is not None:
                row.genealogical_board_quorum = max(1, min(12, int(genealogical_board_quorum)))
            row.updated_by = actor_id
            row.updated_at_utc = now
            row.reason = reason.strip() or "Delegated onboarding configuration updated"
            self._record_db_audit(
                db,
                tenant_id="ENCLAVE",
                actor_id=actor_id,
                action="DELEGATION_CONFIG_UPDATED",
                payload=self._serialize_policy(row),
                recorded_at=now,
            )
            db.commit()
            db.refresh(row)
            serialized = self._serialize_policy(row)

        audit_evt = get_governance_audit_log().record(
            event_type="DELEGATION_CONFIG_UPDATED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id="DELEGATED_ONBOARDING_CONFIG",
            action="UPDATE_DELEGATION_CONFIG",
            outcome="UPDATED",
            http_status=200,
            detail=(
                f"Delegated onboarding scope={serialized['delegated_onboarding_scope']}, "
                f"admission_authority_mode={serialized['admission_authority_mode']}, "
                f"genealogical_board_enabled={serialized['genealogical_board_enabled']}."
            ),
        )
        return {**serialized, "audit_event_id": audit_evt["event_id"]}

    def submit_delegated_dossier(
        self,
        payload: Dict[str, Any],
        *,
        actor_role: Optional[str] = None,
        actor_id: str = "",
        actor_house_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Stage 1: Authorized ranked officer submits an admission dossier strictly into PENDING_RATIFICATION."""
        self._ensure_ready()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="Payload must be a JSON object.")

        # Strict ADR-011 & PII air-gap scan before anything else
        _reject_pii_and_banking_payload(payload)

        norm_role = canonical_registry_role(actor_role or payload.get("actor_role"))
        clean_actor_id = (actor_id or str(payload.get("actor_id") or "") or norm_role or "unknown").strip()

        if is_class_t_role(norm_role) or norm_role not in DELEGATED_SUBMITTER_ROLES:
            get_governance_audit_log().record(
                event_type="DELEGATED_ONBOARDING_DENIED",
                actor_id=clean_actor_id,
                actor_role=norm_role or "UNSPECIFIED",
                target_id="DELEGATED_SUBMIT",
                action="DELEGATED_ONBOARDING_SUBMIT",
                outcome="DENIED_UNAUTHORIZED_ROLE",
                http_status=403,
                detail=f"Role '{norm_role or 'UNSPECIFIED'}' is not authorized to submit delegated onboarding dossiers.",
            )
            raise HTTPException(
                status_code=403,
                detail=f"UNAUTHORIZED_DELEGATED_SUBMITTER: Role '{norm_role or 'UNSPECIFIED'}' cannot submit delegated admission dossiers.",
            )

        house_input = payload.get("target_house_id") if payload.get("target_house_id") is not None else payload.get("lineage_house")
        try:
            target_house_id, lineage_code = validate_lineage_house(house_input)
        except OnboardingValidationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        with self._session_factory() as db:
            policy_row = db.get(EnclavePolicyControlModel, "GLOBAL")
            policy = self._serialize_policy(policy_row)

            # Enforce Chief Admin delegation scope gate
            if norm_role != "CHIEF_ADMIN":
                scope = policy["delegated_onboarding_scope"]
                if scope == DELEGATION_SCOPE_ADMIN_ONLY:
                    get_governance_audit_log().record(
                        event_type="DELEGATED_ONBOARDING_DENIED",
                        actor_id=clean_actor_id,
                        actor_role=norm_role,
                        target_id=lineage_code,
                        action="DELEGATED_ONBOARDING_SUBMIT",
                        outcome="DENIED_ADMIN_ONLY_MODE",
                        http_status=403,
                        detail="Delegated onboarding is disabled (ADMIN_ONLY mode active).",
                    )
                    raise HTTPException(
                        status_code=403,
                        detail="DELEGATED_ONBOARDING_DISABLED: Enclave onboarding scope is currently ADMIN_ONLY.",
                    )
                if scope == DELEGATION_SCOPE_PER_HOUSE:
                    if not policy["house_delegation_flags"].get(str(target_house_id), False):
                        get_governance_audit_log().record(
                            event_type="DELEGATED_ONBOARDING_DENIED",
                            actor_id=clean_actor_id,
                            actor_role=norm_role,
                            target_id=lineage_code,
                            action="DELEGATED_ONBOARDING_SUBMIT",
                            outcome="DENIED_HOUSE_DELEGATION_OFF",
                            http_status=403,
                            detail=f"Delegated onboarding is not enabled for {lineage_code}.",
                        )
                        raise HTTPException(
                            status_code=403,
                            detail=f"HOUSE_DELEGATION_NOT_ENABLED: Delegated onboarding is disabled for {lineage_code}.",
                        )
                # Verify officer's live DB role & House boundary (fail closed across Houses!)
                officer_rows = (
                    db.query(UserRoleAssignmentModel)
                    .filter(UserRoleAssignmentModel.member_id == clean_actor_id)
                    .all()
                )
                if officer_rows:
                    active_officer_roles = [r for r in officer_rows if r.status == "ACTIVE"]
                    if not any(r.role_token in DELEGATED_SUBMITTER_ROLES for r in active_officer_roles):
                        raise HTTPException(
                            status_code=403,
                            detail=f"OFFICER_ROLE_REVOKED: {clean_actor_id} no longer holds an active delegated onboarding role.",
                        )
                    officer_houses = {int(r.house_id) for r in active_officer_roles if r.house_id is not None}
                    if officer_houses and target_house_id not in officer_houses:
                        get_governance_audit_log().record(
                            event_type="DELEGATED_ONBOARDING_DENIED",
                            actor_id=clean_actor_id,
                            actor_role=norm_role,
                            target_id=lineage_code,
                            action="DELEGATED_ONBOARDING_SUBMIT",
                            outcome="DENIED_CROSS_HOUSE",
                            http_status=403,
                            detail=f"Cross-house intake denied: officer {clean_actor_id} ({norm_role}) cannot submit for {lineage_code}.",
                        )
                        raise HTTPException(
                            status_code=403,
                            detail=f"CROSS_HOUSE_DELEGATION_FORBIDDEN: Officer {clean_actor_id} cannot submit dossiers for {lineage_code}.",
                        )
                if actor_house_id is not None and int(actor_house_id) != int(target_house_id):
                    get_governance_audit_log().record(
                        event_type="DELEGATED_ONBOARDING_DENIED",
                        actor_id=clean_actor_id,
                        actor_role=norm_role,
                        target_id=lineage_code,
                        action="DELEGATED_ONBOARDING_SUBMIT",
                        outcome="DENIED_CROSS_HOUSE",
                        http_status=403,
                        detail=f"Cross-house intake denied: HOUSE-{int(actor_house_id):02d} cannot submit for {lineage_code}.",
                    )
                    raise HTTPException(
                        status_code=403,
                        detail=f"CROSS_HOUSE_DELEGATION_FORBIDDEN: Officer scoped to HOUSE-{int(actor_house_id):02d} cannot submit for {lineage_code}.",
                    )

            # Validate dossier fields (ADR-008 integer cents, ADR-011 opaque token, kinship & attestation)
            full_name = str(payload.get("applicant_full_name") or payload.get("full_name") or "").strip()
            if len(full_name) < 2 or len(full_name) > 120:
                raise HTTPException(status_code=422, detail="applicant_full_name must be between 2 and 120 characters.")

            raw_applicant_email = payload.get("applicant_email") if payload.get("applicant_email") is not None else payload.get("email")
            applicant_email: Optional[str] = None
            if raw_applicant_email is not None and str(raw_applicant_email).strip():
                try:
                    applicant_email = validate_optional_email(
                        raw_applicant_email,
                        fallback_member_id=str(payload.get("applicant_member_id") or full_name),
                    )
                except OnboardingValidationError as exc:
                    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

            kinship = str(payload.get("kinship_verification") or "").strip()
            if len(kinship) < 5:
                raise HTTPException(status_code=422, detail="kinship_verification proof summary is required.")

            attestation = str(payload.get("due_diligence_attestation") or "").strip()
            if len(attestation) < 5:
                raise HTTPException(status_code=422, detail="Signed due_diligence_attestation is required.")

            custodial_status = str(payload.get("custodial_status") or "ADULT").strip().upper()
            if custodial_status not in {"ADULT", "MINOR_CUSTODIAL"}:
                raise HTTPException(status_code=422, detail="custodial_status must be ADULT or MINOR_CUSTODIAL.")
            is_custodial = custodial_status == "MINOR_CUSTODIAL" or bool(payload.get("is_custodial", False))
            if is_custodial:
                custodial_status = "MINOR_CUSTODIAL"

            pay_it_forward = bool(payload.get("pay_it_forward_sponsored", False))
            sponsor_id = str(payload.get("sponsor_member_id") or "").strip() or None

            try:
                seed_cents = validate_exact_cents(payload.get("seed_cents", 0))
                risk_dial_bps = validate_risk_dial_bps(
                    risk_dial_pct=payload.get("risk_dial_pct"),
                    risk_dial_bps=payload.get("risk_dial_bps"),
                )
                bank_ref_token = validate_opaque_bank_ref(payload.get("bank_ref_token"))
            except OnboardingValidationError as exc:
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

            now = _utc_now()
            dossier_id = f"DOS-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:8].upper()}"
            sig_material = f"{dossier_id}|{full_name}|{lineage_code}|{kinship}|{attestation}|{clean_actor_id}|{now}"
            attestation_sig = hashlib.sha256(sig_material.encode("utf-8")).hexdigest()

            dossier = DelegatedOnboardingDossierModel(
                dossier_id=dossier_id,
                applicant_full_name=full_name,
                applicant_email=applicant_email,
                applicant_member_id=str(payload.get("applicant_member_id") or "").strip() or None,
                target_house_id=target_house_id,
                lineage_code=lineage_code,
                kinship_verification=kinship,
                custodial_status=custodial_status,
                is_custodial=1 if is_custodial else 0,
                pay_it_forward_sponsored=1 if pay_it_forward else 0,
                sponsor_member_id=sponsor_id,
                seed_cents=seed_cents,
                risk_dial_bps=risk_dial_bps,
                bank_ref_token=bank_ref_token,
                due_diligence_attestation=attestation,
                attestation_signature=attestation_sig,
                submitted_by_member_id=clean_actor_id,
                submitted_by_role=norm_role,
                submitted_by_house_id=actor_house_id,
                status=DOSSIER_PENDING_RATIFICATION,
                board_votes_json="[]",
                created_at_utc=now,
                updated_at_utc=now,
            )
            db.add(dossier)
            self._record_db_audit(
                db,
                tenant_id=lineage_code,
                actor_id=clean_actor_id,
                action="DELEGATED_DOSSIER_SUBMITTED",
                payload={
                    "dossier_id": dossier_id,
                    "applicant_full_name": full_name,
                    "lineage_code": lineage_code,
                    "status": DOSSIER_PENDING_RATIFICATION,
                    "scma_activated": False,
                    "attestation_signature": attestation_sig,
                },
                recorded_at=now,
            )
            db.commit()
            db.refresh(dossier)
            serialized = self._serialize_dossier(dossier)

        audit_evt = get_governance_audit_log().record(
            event_type="DELEGATED_DOSSIER_SUBMITTED",
            actor_id=clean_actor_id,
            actor_role=norm_role,
            target_id=serialized["dossier_id"],
            action="DELEGATED_ONBOARDING_SUBMIT",
            outcome="PENDING_RATIFICATION",
            http_status=201,
            detail=(
                f"{norm_role} ({clean_actor_id}) submitted admission dossier {serialized['dossier_id']} "
                f"for {serialized['applicant_full_name']} ({lineage_code}) -> PENDING_RATIFICATION (zero SCMA activation)."
            ),
        )
        return {
            "status": DOSSIER_PENDING_RATIFICATION,
            "scma_provisioned": False,
            "dossier": serialized,
            "audit_event_id": audit_evt["event_id"],
        }

    def list_dossiers(
        self,
        *,
        status: Optional[str] = None,
        house_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_ready()
        with self._session_factory() as db:
            q = db.query(DelegatedOnboardingDossierModel)
            if status:
                q = q.filter(DelegatedOnboardingDossierModel.status == status.strip().upper())
            if house_id is not None:
                q = q.filter(DelegatedOnboardingDossierModel.target_house_id == int(house_id))
            rows = q.order_by(DelegatedOnboardingDossierModel.created_at_utc.desc()).all()
            return [self._serialize_dossier(r) for r in rows]

    def get_dossier(self, dossier_id: str) -> Dict[str, Any]:
        self._ensure_ready()
        with self._session_factory() as db:
            row = db.get(DelegatedOnboardingDossierModel, dossier_id)
            if row is None:
                raise HTTPException(status_code=404, detail=f"Onboarding dossier '{dossier_id}' not found.")
            return self._serialize_dossier(row)

    def cast_board_vote(
        self,
        *,
        dossier_id: str,
        vote: str,
        rationale: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = "",
        actor_house_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Stage 2 (Optional): Genealogical Admissions Board vote (HOUSE_GENEALOGIST / H2)."""
        self._ensure_ready()
        norm_role = canonical_registry_role(actor_role)
        clean_actor = (actor_id or norm_role or "unknown").strip()
        if norm_role not in GENEALOGICAL_BOARD_ROLES:
            raise HTTPException(
                status_code=403,
                detail="GENEALOGICAL_BOARD_ROLE_REQUIRED: Only HOUSE_GENEALOGIST, H2, or Chief Admin may cast board votes.",
            )
        vote_norm = str(vote or "").strip().upper()
        if vote_norm not in {"APPROVE", "REJECT", "REQUEST_PROOF"}:
            raise HTTPException(status_code=422, detail="vote must be APPROVE, REJECT, or REQUEST_PROOF.")

        now = _utc_now()
        with self._session_factory() as db:
            policy = self._serialize_policy(db.get(EnclavePolicyControlModel, "GLOBAL"))
            if not policy["genealogical_board_enabled"]:
                raise HTTPException(
                    status_code=403,
                    detail="GENEALOGICAL_BOARD_DORMANT: Genealogical Admissions Board voting is currently disabled by Chief Administrator.",
                )

            dossier = db.get(DelegatedOnboardingDossierModel, dossier_id)
            if dossier is None:
                raise HTTPException(status_code=404, detail=f"Onboarding dossier '{dossier_id}' not found.")
            if (
                norm_role != "CHIEF_ADMIN"
                and actor_house_id is not None
                and int(actor_house_id) != int(dossier.target_house_id)
            ):
                raise HTTPException(
                    status_code=403,
                    detail=f"CROSS_HOUSE_BOARD_VOTE_FORBIDDEN: Officer scoped to HOUSE-{int(actor_house_id):02d} cannot vote on {dossier.lineage_code} dossier.",
                )
            if dossier.status in {DOSSIER_RATIFIED_PROVISIONED, DOSSIER_REJECTED}:
                raise HTTPException(status_code=409, detail=f"Dossier {dossier_id} is already closed ({dossier.status}).")

            votes: List[Dict[str, Any]] = json.loads(dossier.board_votes_json or "[]")
            votes = [v for v in votes if v.get("voter_id") != clean_actor]
            votes.append(
                {
                    "voter_id": clean_actor,
                    "voter_role": norm_role,
                    "vote": vote_norm,
                    "rationale": rationale.strip(),
                    "cast_at_utc": now,
                }
            )
            dossier.board_votes_json = json.dumps(votes)
            approve_count = sum(1 for v in votes if v.get("vote") == "APPROVE")
            if vote_norm == "REQUEST_PROOF":
                dossier.status = DOSSIER_PROOF_REQUESTED
            elif approve_count >= int(policy["genealogical_board_quorum"]):
                dossier.status = DOSSIER_BOARD_RECOMMENDED
            else:
                dossier.status = DOSSIER_PENDING_RATIFICATION
            dossier.updated_at_utc = now
            db.commit()
            db.refresh(dossier)
            serialized = self._serialize_dossier(dossier)

        audit_evt = get_governance_audit_log().record(
            event_type="GENEALOGICAL_BOARD_VOTE",
            actor_id=clean_actor,
            actor_role=norm_role,
            target_id=dossier_id,
            action=f"BOARD_VOTE_{vote_norm}",
            outcome=serialized["status"],
            http_status=200,
            detail=f"{norm_role} ({clean_actor}) voted {vote_norm} on dossier {dossier_id} -> {serialized['status']}.",
        )
        return {
            "status": serialized["status"],
            "scma_provisioned": False,
            "dossier": serialized,
            "audit_event_id": audit_evt["event_id"],
        }

    def cosign_dossier(
        self,
        *,
        dossier_id: str,
        notes: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = "",
        actor_house_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """PR #99 Two-Party Admission Co-Sign strictly for authorized F2-H (for their assigned House)
        or CHIEF_ADMIN read-only audit inspection. Fails closed HTTP 403 for unauthorized roles/houses.
        """
        self._ensure_ready()
        _reject_pii_and_banking_payload({"notes": notes})

        norm_role = canonical_registry_role(actor_role)
        clean_actor = (actor_id or norm_role or "unknown").strip()

        if is_class_t_role(norm_role) or norm_role not in {"F2-H", "CHIEF_ADMIN"}:
            get_governance_audit_log().record(
                event_type="DOSSIER_COSIGN_DENIED",
                actor_id=clean_actor,
                actor_role=norm_role or "UNSPECIFIED",
                target_id=dossier_id,
                action="COSIGN_DOSSIER",
                outcome="DENIED_UNAUTHORIZED_ROLE",
                http_status=403,
                detail=f"Role '{norm_role or 'UNSPECIFIED'}' is not authorized to co-sign admission dossiers (F2-H required).",
            )
            raise HTTPException(
                status_code=403,
                detail=f"COSIGN_ROLE_FORBIDDEN: Role '{norm_role or 'UNSPECIFIED'}' cannot execute F2-H admission co-sign.",
            )

        now = _utc_now()
        with self._session_factory() as db:
            dossier = db.get(DelegatedOnboardingDossierModel, dossier_id)
            if dossier is None:
                raise HTTPException(status_code=404, detail=f"Onboarding dossier '{dossier_id}' not found.")

            # Chief Admin audit inspection path — never forges F2-H co-signature
            if norm_role == "CHIEF_ADMIN":
                serialized = self._serialize_dossier(dossier)
                audit_evt = get_governance_audit_log().record(
                    event_type="DOSSIER_COSIGN_AUDIT_INSPECTED",
                    actor_id=clean_actor,
                    actor_role="CHIEF_ADMINISTRATOR",
                    target_id=dossier_id,
                    action="COSIGN_AUDIT_INSPECT",
                    outcome="INSPECTED_READ_ONLY",
                    http_status=200,
                    detail=f"Chief Admin inspected two-party co-sign status on dossier {dossier_id} (f2h_cosigned={serialized['f2h_cosigned']}).",
                )
                return {
                    "status": "AUDIT_INSPECTION_ONLY",
                    "f2h_cosigned": serialized["f2h_cosigned"],
                    "scma_provisioned": False,
                    "dossier": serialized,
                    "audit_event_id": audit_evt["event_id"],
                }

            if dossier.status in {DOSSIER_RATIFIED_PROVISIONED, DOSSIER_REJECTED}:
                raise HTTPException(
                    status_code=409,
                    detail=f"Dossier {dossier_id} is already finalized ({dossier.status}).",
                )

            # Enforce strict House boundary for F2-H officer
            officer_rows = (
                db.query(UserRoleAssignmentModel)
                .filter(UserRoleAssignmentModel.member_id == clean_actor)
                .all()
            )
            officer_f2h_houses: Set[int] = set()
            if officer_rows:
                active_f2h = [r for r in officer_rows if r.status == "ACTIVE" and r.role_token == "F2-H"]
                if not active_f2h:
                    get_governance_audit_log().record(
                        event_type="DOSSIER_COSIGN_DENIED",
                        actor_id=clean_actor,
                        actor_role="F2-H",
                        target_id=dossier_id,
                        action="COSIGN_DOSSIER",
                        outcome="DENIED_ROLE_REVOKED",
                        http_status=403,
                        detail=f"Officer {clean_actor} no longer holds an ACTIVE F2-H assignment.",
                    )
                    raise HTTPException(
                        status_code=403,
                        detail=f"OFFICER_ROLE_REVOKED: {clean_actor} does not hold an active F2-H seat.",
                    )
                officer_f2h_houses = {int(r.house_id) for r in active_f2h if r.house_id is not None}
                if officer_f2h_houses and int(dossier.target_house_id) not in officer_f2h_houses:
                    get_governance_audit_log().record(
                        event_type="DOSSIER_COSIGN_DENIED",
                        actor_id=clean_actor,
                        actor_role="F2-H",
                        target_id=dossier_id,
                        action="COSIGN_DOSSIER",
                        outcome="DENIED_CROSS_HOUSE",
                        http_status=403,
                        detail=f"Cross-house F2-H co-sign denied: {clean_actor} is assigned to {sorted(officer_f2h_houses)}, not {dossier.lineage_code}.",
                    )
                    raise HTTPException(
                        status_code=403,
                        detail=f"CROSS_HOUSE_COSIGN_FORBIDDEN: F2-H officer {clean_actor} cannot co-sign dossiers for {dossier.lineage_code}.",
                    )

            if actor_house_id is not None and int(actor_house_id) != int(dossier.target_house_id):
                get_governance_audit_log().record(
                    event_type="DOSSIER_COSIGN_DENIED",
                    actor_id=clean_actor,
                    actor_role="F2-H",
                    target_id=dossier_id,
                    action="COSIGN_DOSSIER",
                    outcome="DENIED_CROSS_HOUSE",
                    http_status=403,
                    detail=f"Cross-house F2-H co-sign denied: HOUSE-{int(actor_house_id):02d} cannot co-sign {dossier.lineage_code}.",
                )
                raise HTTPException(
                    status_code=403,
                    detail=f"CROSS_HOUSE_COSIGN_FORBIDDEN: F2-H scoped to HOUSE-{int(actor_house_id):02d} cannot co-sign for {dossier.lineage_code}.",
                )

            if actor_house_id is None and not officer_f2h_houses:
                get_governance_audit_log().record(
                    event_type="DOSSIER_COSIGN_DENIED",
                    actor_id=clean_actor,
                    actor_role="F2-H",
                    target_id=dossier_id,
                    action="COSIGN_DOSSIER",
                    outcome="DENIED_HOUSE_SCOPE_REQUIRED",
                    http_status=403,
                    detail="F2-H co-sign requires explicit X-House-ID or assigned House scope.",
                )
                raise HTTPException(
                    status_code=403,
                    detail="HOUSE_SCOPE_REQUIRED: F2-H co-sign requires an assigned House matching the dossier's target House.",
                )

            clean_notes = notes.strip() or f"F2-H House Head attestation for {dossier.lineage_code}"
            cosign_sig = hashlib.sha256(
                f"{dossier_id}|{dossier.target_house_id}|{clean_actor}|F2-H|{clean_notes}|{now}".encode("utf-8")
            ).hexdigest()

            dossier.f2h_cosigned_by = clean_actor
            dossier.f2h_cosigned_role = "F2-H"
            dossier.f2h_cosigned_house_id = int(dossier.target_house_id)
            dossier.f2h_cosigned_at_utc = now
            dossier.f2h_cosign_notes = clean_notes
            dossier.f2h_cosign_signature = cosign_sig
            dossier.updated_at_utc = now

            self._record_db_audit(
                db,
                tenant_id=dossier.lineage_code,
                actor_id=clean_actor,
                action="DOSSIER_F2H_COSIGNED",
                payload={
                    "dossier_id": dossier_id,
                    "target_house_id": int(dossier.target_house_id),
                    "f2h_cosigned_by": clean_actor,
                    "f2h_cosign_signature": cosign_sig,
                    "scma_provisioned": False,
                },
                recorded_at=now,
            )
            db.commit()
            db.refresh(dossier)
            serialized = self._serialize_dossier(dossier)

        audit_evt = get_governance_audit_log().record(
            event_type="DOSSIER_F2H_COSIGNED",
            actor_id=clean_actor,
            actor_role="F2-H",
            target_id=dossier_id,
            action="COSIGN_DOSSIER",
            outcome="F2H_COSIGNED",
            http_status=200,
            detail=(
                f"F2-H ({clean_actor}) co-signed admission dossier {dossier_id} for "
                f"{serialized['lineage_code']} (awaiting Chief Admin final ratification)."
            ),
        )
        return {
            "status": "F2H_COSIGNED",
            "f2h_cosigned": True,
            "scma_provisioned": False,
            "dossier": serialized,
            "audit_event_id": audit_evt["event_id"],
        }

    def request_dossier_proof(
        self,
        *,
        dossier_id: str,
        proof_request: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = FOUNDER_MEMBER_ID,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        norm_role = canonical_registry_role(actor_role)
        clean_actor = (actor_id or norm_role or "unknown").strip()
        with self._session_factory() as db:
            policy = self._serialize_policy(db.get(EnclavePolicyControlModel, "GLOBAL"))
            if norm_role != "CHIEF_ADMIN":
                if not (policy["genealogical_board_enabled"] and norm_role in GENEALOGICAL_BOARD_ROLES):
                    raise HTTPException(
                        status_code=403,
                        detail="Only Chief Administrator or an active Genealogical Board member may request additional proof.",
                    )
            dossier = db.get(DelegatedOnboardingDossierModel, dossier_id)
            if dossier is None:
                raise HTTPException(status_code=404, detail=f"Onboarding dossier '{dossier_id}' not found.")
            if dossier.status in {DOSSIER_RATIFIED_PROVISIONED, DOSSIER_REJECTED}:
                raise HTTPException(status_code=409, detail=f"Dossier {dossier_id} is already finalized ({dossier.status}).")
            now = _utc_now()
            dossier.status = DOSSIER_PROOF_REQUESTED
            dossier.decision_notes = proof_request.strip() or "Additional genealogical/kinship proof requested."
            dossier.updated_at_utc = now
            db.commit()
            db.refresh(dossier)
            serialized = self._serialize_dossier(dossier)

        audit_evt = get_governance_audit_log().record(
            event_type="DELEGATED_DOSSIER_PROOF_REQUESTED",
            actor_id=clean_actor,
            actor_role=norm_role or "CHIEF_ADMINISTRATOR",
            target_id=dossier_id,
            action="REQUEST_DOSSIER_PROOF",
            outcome=DOSSIER_PROOF_REQUESTED,
            http_status=200,
            detail=f"Requested additional proof on dossier {dossier_id}: {serialized['decision_notes']}",
        )
        return {"status": DOSSIER_PROOF_REQUESTED, "dossier": serialized, "audit_event_id": audit_evt["event_id"]}

    def reject_dossier(
        self,
        *,
        dossier_id: str,
        reason: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = FOUNDER_MEMBER_ID,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="REJECT_DOSSIER",
            target_id=dossier_id,
        )
        now = _utc_now()
        with self._session_factory() as db:
            dossier = db.get(DelegatedOnboardingDossierModel, dossier_id)
            if dossier is None:
                raise HTTPException(status_code=404, detail=f"Onboarding dossier '{dossier_id}' not found.")
            if dossier.status == DOSSIER_RATIFIED_PROVISIONED:
                raise HTTPException(status_code=409, detail=f"Dossier {dossier_id} was already ratified and provisioned.")
            dossier.status = DOSSIER_REJECTED
            dossier.ratified_by = actor_id
            dossier.ratified_at_utc = now
            dossier.decision_notes = reason.strip() or "Rejected by Chief Administrator."
            dossier.updated_at_utc = now
            db.commit()
            db.refresh(dossier)
            serialized = self._serialize_dossier(dossier)

        audit_evt = get_governance_audit_log().record(
            event_type="DELEGATED_DOSSIER_REJECTED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=dossier_id,
            action="REJECT_DOSSIER",
            outcome=DOSSIER_REJECTED,
            http_status=200,
            detail=f"Rejected admission dossier {dossier_id}: {serialized['decision_notes']}",
        )
        return {"status": DOSSIER_REJECTED, "dossier": serialized, "audit_event_id": audit_evt["event_id"]}

    def ratify_dossier(
        self,
        *,
        dossier_id: str,
        decision_notes: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = FOUNDER_MEMBER_ID,
    ) -> Dict[str, Any]:
        """
        Stage 2 -> Stage 3 Atomic Dual-Plane Provisioning:
        1. Chief Admin ratifies dossier (enforcing TWO_PARTY_COSIGN_REQUIRED HTTP 409 if
           admission_authority_mode == TWO_PARTY_COSIGN and F2-H co-sign is missing).
        2. Provisions member SCMA, House lineage, initial MEMBER_USER role, PR #98 private
           family allowlist AuthUserModel (`authorized_hats=["CLASS_M"]`, `is_apex_tier3=False`),
           and initial custodial mentor (INTRA_HOUSE or CROSS_HOUSE_ANTI_TRIBAL per active mode).
        3. Emits signed HMAC-SHA256 MEMBER_ADMISSION_RATIFIED JSON-LD event to the ADR-011
           accounting outbox (both global_accounting_gateway and accounting_outbox_events table),
           with zero bank account numbers, routing numbers, or SSNs.
        """
        self._ensure_ready()
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="RATIFY_DOSSIER",
            target_id=dossier_id,
        )

        # Read and validate dossier state + admission authority mode BEFORE any provisioning
        with self._session_factory() as db:
            dossier = db.get(DelegatedOnboardingDossierModel, dossier_id)
            if dossier is None:
                raise HTTPException(status_code=404, detail=f"Onboarding dossier '{dossier_id}' not found.")
            if dossier.status == DOSSIER_RATIFIED_PROVISIONED:
                raise HTTPException(status_code=409, detail=f"Dossier {dossier_id} has already been ratified and provisioned.")
            if dossier.status == DOSSIER_REJECTED:
                raise HTTPException(status_code=409, detail=f"Dossier {dossier_id} was rejected and cannot be ratified.")

            policy_row = db.get(EnclavePolicyControlModel, "GLOBAL")
            admission_mode = (
                getattr(policy_row, "admission_authority_mode", None)
                if policy_row is not None
                else ADMISSION_MODE_CHIEF_ADMIN_SOLO
            ) or ADMISSION_MODE_CHIEF_ADMIN_SOLO

            f2h_cosigned_by = getattr(dossier, "f2h_cosigned_by", None)
            f2h_cosigned_role = getattr(dossier, "f2h_cosigned_role", None)
            f2h_cosigned_house_id = getattr(dossier, "f2h_cosigned_house_id", None)
            f2h_cosigned_at_utc = getattr(dossier, "f2h_cosigned_at_utc", None)

            if admission_mode == ADMISSION_MODE_TWO_PARTY_COSIGN:
                has_valid_cosign = (
                    bool(f2h_cosigned_by)
                    and bool(f2h_cosigned_at_utc)
                    and f2h_cosigned_role == "F2-H"
                    and int(f2h_cosigned_house_id or 0) == int(dossier.target_house_id)
                )
                if not has_valid_cosign:
                    get_governance_audit_log().record(
                        event_type="MEMBER_ADMISSION_COSIGN_REQUIRED",
                        actor_id=actor_id,
                        actor_role="CHIEF_ADMINISTRATOR",
                        target_id=dossier_id,
                        action="RATIFY_DOSSIER",
                        outcome="BLOCKED_TWO_PARTY_COSIGN_REQUIRED",
                        http_status=409,
                        detail=(
                            f"Blocked Chief Admin solo ratification of dossier {dossier_id}: "
                            f"admission_authority_mode=TWO_PARTY_COSIGN requires an authorized F2-H "
                            f"House Head co-signature for {dossier.lineage_code}."
                        ),
                    )
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"TWO_PARTY_COSIGN_REQUIRED: Dossier {dossier_id} requires an authorized "
                            f"F2-H House Head co-sign for {dossier.lineage_code} prior to Chief Administrator final ratification."
                        ),
                    )

            provision_payload: Dict[str, Any] = {
                "full_name": dossier.applicant_full_name,
                "lineage_house": dossier.lineage_code,
                "role_tier": "MEMBER_USER",
                "seed_cents": int(dossier.seed_cents),
                "risk_dial_bps": int(dossier.risk_dial_bps),
                "is_custodial": bool(dossier.is_custodial),
                "bank_ref_token": dossier.bank_ref_token,
            }
            if getattr(dossier, "applicant_email", None):
                provision_payload["email"] = dossier.applicant_email
            if dossier.applicant_member_id:
                provision_payload["member_id"] = dossier.applicant_member_id
            target_house_id = int(dossier.target_house_id)
            custodial_status = dossier.custodial_status
            pay_it_forward_sponsored = bool(dossier.pay_it_forward_sponsored)
            sponsor_member_id = dossier.sponsor_member_id
            lineage_code = dossier.lineage_code

        # Stage 3A: Provision SCMA + Invite Token + Lineage + CapitalLedger via MemberOnboardingService
        onb_svc = self._get_onboarding_service()
        try:
            receipt = onb_svc.provision_member(provision_payload, created_by=actor_id)
        except OnboardingValidationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        member_info = receipt["member"]
        provisioned_member_id = member_info["member_id"]
        provisioned_scma_id = member_info["scma_id"]
        now = _utc_now()

        # Stage 3B & 3C: Initial MEMBER_USER role + AuthUserModel allowlist + Custodial mentor + Signed ADR-011 IFAS outbox event
        gateway = self._get_accounting_gateway()
        with self._session_factory() as db:
            dossier = db.get(DelegatedOnboardingDossierModel, dossier_id)
            policy_row = db.get(EnclavePolicyControlModel, "GLOBAL")
            active_mode = policy_row.custody_assignment_mode if policy_row else CUSTODY_MODE_INTRA_HOUSE

            # Initial MEMBER_USER role assignment
            role_row = UserRoleAssignmentModel(
                assignment_id=f"ROLE-{uuid.uuid4().hex[:10].upper()}",
                member_id=provisioned_member_id,
                role_token="MEMBER_USER",
                house_id=target_house_id,
                status="ACTIVE",
                assigned_by=actor_id,
                assigned_at_utc=now,
                reason=f"Initial MEMBER_USER provisioned on ratification of {dossier_id}",
            )
            db.add(role_row)

            # Automatically provision/upsert PR #98 private family allowlist login (CLASS_M, non-apex)
            auth_allowlist_user = provision_member_auth_allowlist_in_session(
                db,
                user_id=provisioned_member_id,
                email=member_info["email"],
                display_name=member_info["full_name"],
                scma_id=provisioned_scma_id,
                house_id=lineage_code,
                actor_id=actor_id,
                source="DELEGATED_RATIFICATION",
            )

            # Initial custodial mentor per active INTRA_HOUSE / CROSS_HOUSE_ANTI_TRIBAL mode
            cust_id, cust_role, _ = self._select_eligible_custodian_in_tx(
                db,
                charge_house_id=target_house_id,
                exclude_member_ids={provisioned_member_id},
                mode=active_mode,
            )
            custody_row = CustodialAssignmentModel(
                custody_id=f"CUST-{uuid.uuid4().hex[:10].upper()}",
                custodian_member_id=cust_id,
                custodian_role=cust_role,
                charge_member_id=provisioned_member_id,
                charge_scma_id=provisioned_scma_id,
                charge_house_id=target_house_id,
                assignment_mode=active_mode,
                active=1,
                assigned_by=actor_id,
                assigned_at_utc=now,
                reason=f"Initial custodial assignment on ratification of {dossier_id} ({active_mode})",
            )
            db.add(custody_row)

            # Ensure monotonic sequence across both in-memory gateway and relational accounting_outbox_events
            db_max_seq = db.query(func.max(AccountingOutboxEventModel.sequence_id)).scalar() or 0
            if int(db_max_seq) > int(gateway._seq_counter):
                gateway._seq_counter = int(db_max_seq)

            ifas_payload = {
                "@context": "https://schema.pdeue.org/accounting/v1",
                "@type": "MemberAdmissionRatifiedEvent",
                "event_type": "MEMBER_ADMISSION_RATIFIED",
                "timestamp": now,
                "dossier_id": dossier_id,
                "member_id": provisioned_member_id,
                "scma_id": provisioned_scma_id,
                "house_id": target_house_id,
                "lineage_code": lineage_code,
                "custodial_status": custodial_status,
                "is_custodial": bool(member_info["is_custodial"]),
                "pay_it_forward_sponsored": pay_it_forward_sponsored,
                "sponsor_member_id": sponsor_member_id,
                "seed_cents": int(member_info["seed_cents"]),
                "high_water_mark_cents": int(member_info["high_water_mark_cents"]),
                "bank_ref_token": member_info["bank_ref_token"],
                "custodian_member_id": cust_id,
                "custody_assignment_mode": active_mode,
                "admission_authority_mode": admission_mode,
                "f2h_cosigned_by": f2h_cosigned_by,
                "f2h_cosigned_at_utc": f2h_cosigned_at_utc,
                "ratified_by": actor_id,
                "ratified_at_utc": now,
            }
            # Final defense-in-depth scan against banking/PII leakage before staging
            _reject_pii_and_banking_payload(ifas_payload)
            signed_envelope = gateway.stage_event(ifas_payload)

            db.add(
                AccountingOutboxEventModel(
                    event_id=signed_envelope["event_id"],
                    sequence_id=int(signed_envelope["sequence_id"]),
                    event_type="MEMBER_ADMISSION_RATIFIED",
                    payload_json=json.dumps(signed_envelope["payload"], sort_keys=True),
                    signature_hmac_sha256=signed_envelope["signature_hmac_sha256"],
                    status=signed_envelope["status"],
                    created_at=signed_envelope["timestamp"],
                )
            )

            # Update dossier to RATIFIED_PROVISIONED
            dossier.status = DOSSIER_RATIFIED_PROVISIONED
            dossier.ratified_by = actor_id
            dossier.ratified_at_utc = now
            dossier.decision_notes = decision_notes.strip() or "Ratified and dual-plane provisioned (PDEUE + IFAS outbox)."
            dossier.provisioned_member_id = provisioned_member_id
            dossier.provisioned_scma_id = provisioned_scma_id
            dossier.assigned_custodian_member_id = cust_id
            dossier.ifas_outbox_event_id = signed_envelope["event_id"]
            dossier.updated_at_utc = now

            self._record_db_audit(
                db,
                tenant_id=lineage_code,
                actor_id=actor_id,
                action="MEMBER_ADMISSION_RATIFIED",
                payload={
                    "dossier_id": dossier_id,
                    "member_id": provisioned_member_id,
                    "scma_id": provisioned_scma_id,
                    "custodian_member_id": cust_id,
                    "custody_assignment_mode": active_mode,
                    "admission_authority_mode": admission_mode,
                    "f2h_cosigned_by": f2h_cosigned_by,
                    "auth_allowlist_provisioned": True,
                    "ifas_outbox_event_id": signed_envelope["event_id"],
                },
                recorded_at=now,
            )
            db.commit()
            db.refresh(dossier)
            db.refresh(custody_row)
            serialized_dossier = self._serialize_dossier(dossier)
            serialized_custody = self._serialize_custody(custody_row)
            serialized_role = self._serialize_role(role_row)

        audit_evt = get_governance_audit_log().record(
            event_type="MEMBER_ADMISSION_RATIFIED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=dossier_id,
            action="RATIFY_DOSSIER",
            outcome="RATIFIED_PROVISIONED",
            http_status=200,
            detail=(
                f"Ratified dossier {dossier_id} ({admission_mode}): provisioned {provisioned_scma_id} ({lineage_code}), "
                f"assigned custodian {cust_id} ({active_mode}), provisioned AuthUserModel allowlist, "
                f"emitted signed IFAS outbox event {signed_envelope['event_id']}."
            ),
        )
        return {
            "status": DOSSIER_RATIFIED_PROVISIONED,
            "admission_authority_mode": admission_mode,
            "dossier": serialized_dossier,
            "member": member_info,
            "invite": receipt["invite"],
            "auth_allowlist_user": auth_allowlist_user,
            "role_assignment": serialized_role,
            "custodial_assignment": serialized_custody,
            "ifas_outbox_event": signed_envelope,
            "audit_event_id": audit_evt["event_id"],
        }


_SERVICE_INIT_LOCK = RLock()
_role_custody_service: Optional[RoleCustodyDelegationService] = None


def get_role_custody_service() -> RoleCustodyDelegationService:
    global _role_custody_service
    if _role_custody_service is None:
        with _SERVICE_INIT_LOCK:
            if _role_custody_service is None:
                _role_custody_service = RoleCustodyDelegationService(register_hat_provider=True)
    return _role_custody_service
