"""
Milestone C1 — End-to-End 5-Stage Member Onboarding Pipeline Domain Service.

Preserves all non-negotiable architectural invariants:
- ADR-008: Strict 64-bit integer-cent accounting (floats, decimals, and booleans fail closed).
- ADR-011: Zero banking credentials; opaque bank tokens only (`EXT-REF-[ENTITY]-****[LAST4]`).
- ADR-012 / Rule A14: Initializes `high_water_mark_cents = seed_cents` per SCMA.
- Stage 2: Cryptographically random single-use 48-hour invite activation tokens.
- Stage 4: PDEUE University Chapter 6 certification gate (`PENDING_TUTOR_CERTIFICATION` -> `ACTIVE`).
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import re
import secrets
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from sqlalchemy.orm import Session

from app.db.models import (
    AccountModel,
    AuditLogRecordModel,
    OnboardingInviteTokenModel,
    OnboardingMemberModel,
    UserModel,
)
from app.db.session import Base, SessionLocal, engine as default_engine
from app.domain.capital_ledger import CapitalLedger
from app.domain.lineage_hierarchy import LineageHierarchyService, get_lineage_service
from app.domain.session_auth_service import (
    normalize_email,
    provision_member_auth_allowlist_in_session,
)

ALLOWED_ROLE_TIERS: Tuple[str, ...] = (
    "MEMBER_USER",
    "F1",
    "F2-H",
    "F2-A",
    "F3",
    "T1",
    "T2",
    "T2-HOUSEHOLD",
    "T3",
    "H1",
    "H2",
    "HOUSE_GENEALOGIST",
)
ALLOWED_ROLE_TIER_SET = frozenset(ALLOWED_ROLE_TIERS)

ALLOWED_HOUSES: Tuple[str, ...] = tuple(f"HOUSE-{idx:02d}" for idx in range(1, 13))

INVITE_TTL_HOURS = 48
CERTIFICATION_LEVEL_L1 = "STEWARDSHIP_L1_CERTIFIED"
STATUS_PENDING_CERT = "PENDING_TUTOR_CERTIFICATION"
STATUS_ACTIVE = "ACTIVE"
IFAS_PORTAL_HOST = "accounting.narratix.io"

# Opaque ADR-011 bank reference token format: EXT-REF-[ENTITY]-****[LAST4]
_OPAQUE_BANK_REF_RE = re.compile(r"^EXT-REF-[A-Z0-9][A-Z0-9_-]{1,31}-\*{4}[0-9]{4}$")
# Reject any contiguous sequence of 5+ digits (catches raw routing or bank account numbers).
_RAW_LONG_DIGITS_RE = re.compile(r"\d{5,}")
_RAW_ROUTING_HINT_RE = re.compile(r"(?i)\b(?:aba|routing|swift|iban|acct|account[\s_-]*no)\b")
_RAW_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_EMAIL_BASIC_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,180}\.[^@\s]{2,32}$")

FORBIDDEN_BANKING_KEYS = frozenset(
    {
        "routing_number",
        "aba_routing",
        "aba_number",
        "bank_account_number",
        "account_number",
        "raw_account_number",
        "raw_routing_number",
        "swift_code",
        "bic",
        "iban",
        "bank_password",
        "bank_pin",
        "plaid_access_token",
        "ssn",
        "social_security_number",
        "tax_id",
        "tin",
        "itin",
    }
)


class OnboardingValidationError(ValueError):
    """Raised when an onboarding payload fails ADR-008, ADR-011, or schema invariants."""

    def __init__(self, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


class InviteTokenError(ValueError):
    """Raised when an invite token is missing, malformed, expired, or already consumed."""

    def __init__(self, message: str, *, status_code: int = 400, code: str = "INVALID_TOKEN") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _utc_now(now: Optional[datetime] = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _slugify_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", "", name.upper())
    return (cleaned[:8] or "MEMBER").ljust(4, "X")


def _parse_bool_strict(value: Any, *, field_name: str = "is_custodial") -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "1", "yes"}:
            return True
        if low in {"false", "0", "no", ""}:
            return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise OnboardingValidationError(f"{field_name} must be a boolean value.")


def validate_exact_cents(value: Any, *, allow_integer_string: bool = False) -> int:
    """Enforce ADR-008: exact non-negative 64-bit integer cents; floats and decimals rejected."""
    if isinstance(value, bool):
        raise OnboardingValidationError(
            "ADR-008 violation: seed_cents must be an exact integer (booleans are rejected)."
        )
    if isinstance(value, float):
        raise OnboardingValidationError(
            "ADR-008 violation: floating-point currency inputs are strictly prohibited; supply exact integer cents."
        )
    if isinstance(value, str):
        stripped = value.strip()
        if not allow_integer_string:
            raise OnboardingValidationError(
                "ADR-008 violation: seed_cents must be an exact JSON integer, not a string or decimal."
            )
        if not re.fullmatch(r"\d+", stripped):
            raise OnboardingValidationError(
                f"ADR-008 violation: CSV seed_cents '{stripped}' must be a non-negative integer without decimals or symbols."
            )
        cents = int(stripped)
    elif isinstance(value, int):
        cents = value
    else:
        raise OnboardingValidationError(
            "ADR-008 violation: seed_cents must be an exact integer count of cents."
        )

    if cents < 0:
        raise OnboardingValidationError("ADR-008 violation: seed_cents cannot be negative.")
    if cents > 9_223_372_036_854_775_807:
        raise OnboardingValidationError("ADR-008 violation: seed_cents exceeds 64-bit signed integer limit.")
    return cents


def validate_lineage_house(value: Any) -> Tuple[int, str]:
    """Validate and normalize HOUSE-01..HOUSE-12."""
    if isinstance(value, bool):
        raise OnboardingValidationError("lineage_house must be HOUSE-01 through HOUSE-12.")
    if isinstance(value, int):
        house_id = value
    elif isinstance(value, str):
        raw = value.strip().upper()
        match = re.fullmatch(r"(?:HOUSE-)?0?([1-9]|1[0-2])", raw)
        if not match:
            raise OnboardingValidationError(
                f"Invalid lineage_house '{value}'. Expected HOUSE-01 through HOUSE-12."
            )
        house_id = int(match.group(1))
    else:
        raise OnboardingValidationError("lineage_house must be HOUSE-01 through HOUSE-12.")

    if house_id < 1 or house_id > 12:
        raise OnboardingValidationError(
            f"Invalid lineage_house '{value}'. Expected HOUSE-01 through HOUSE-12."
        )
    return house_id, f"HOUSE-{house_id:02d}"


def validate_role_tier(value: Any) -> str:
    if not isinstance(value, str):
        raise OnboardingValidationError("role_tier must be a string.")
    normalized = value.strip().upper()
    if normalized not in ALLOWED_ROLE_TIER_SET:
        raise OnboardingValidationError(
            f"Invalid role_tier '{value}'. Allowed tiers: {', '.join(ALLOWED_ROLE_TIERS)}."
        )
    return normalized


def validate_risk_dial_bps(
    *,
    risk_dial_pct: Any = None,
    risk_dial_bps: Any = None,
) -> int:
    """Validate downward-only risk dial ceiling strictly within 0.50%–2.00% (50–200 bps)."""
    if risk_dial_bps is not None and not isinstance(risk_dial_bps, bool):
        if isinstance(risk_dial_bps, float):
            raise OnboardingValidationError("risk_dial_bps must be an integer between 50 and 200.")
        try:
            bps = int(risk_dial_bps)
        except (TypeError, ValueError) as exc:
            raise OnboardingValidationError("risk_dial_bps must be an integer between 50 and 200.") from exc
    elif risk_dial_pct is not None and not isinstance(risk_dial_pct, bool):
        try:
            pct = float(risk_dial_pct)
        except (TypeError, ValueError) as exc:
            raise OnboardingValidationError("risk_dial_pct must be between 0.50 and 2.00.") from exc
        if pct < 0.50 or pct > 2.00:
            raise OnboardingValidationError(
                f"Downward-only risk dial ceiling ({pct:.2f}%) must be between 0.50% and 2.00%."
            )
        bps = int(round(pct * 100))
    else:
        bps = 150  # Default 1.50%

    if bps < 50 or bps > 200:
        raise OnboardingValidationError(
            f"Downward-only risk dial ceiling ({bps / 100:.2f}%) must be between 0.50% and 2.00%."
        )
    return bps


def validate_opaque_bank_ref(value: Any) -> str:
    """
    Enforce ADR-011 zero banking credential isolation.
    Only opaque tokens matching EXT-REF-[ENTITY]-****[LAST4] are permitted.
    Any raw routing number, raw bank account number (>4 contiguous digits),
    or credential-like pattern fails closed with HTTP 422.
    """
    if not isinstance(value, str) or not value.strip():
        raise OnboardingValidationError(
            "ADR-011 violation: opaque bank_ref_token (EXT-REF-[ENTITY]-****[LAST4]) is required."
        )
    token = value.strip()
    if _RAW_LONG_DIGITS_RE.search(token):
        raise OnboardingValidationError(
            "ADR-011 violation: raw routing numbers or bank account numbers (>4 contiguous digits) are strictly rejected. Use opaque format EXT-REF-[ENTITY]-****[LAST4]."
        )
    if _RAW_ROUTING_HINT_RE.search(token):
        raise OnboardingValidationError(
            "ADR-011 violation: raw banking identifiers (ABA/routing/SWIFT/IBAN) are strictly prohibited."
        )
    if not _OPAQUE_BANK_REF_RE.fullmatch(token):
        raise OnboardingValidationError(
            f"ADR-011 violation: bank_ref_token '{token}' must strictly match EXT-REF-[ENTITY]-****[LAST4] (uppercase entity code + 4 asterisks + last 4 digits)."
        )
    return token


def reject_forbidden_banking_fields(payload: Dict[str, Any]) -> None:
    """Fail-closed scan rejecting any raw banking credential fields in incoming JSON/CSV dicts."""
    for key in payload.keys():
        if str(key).strip().lower() in FORBIDDEN_BANKING_KEYS:
            raise OnboardingValidationError(
                f"ADR-011 violation: forbidden banking credential field '{key}' is permanently banned from PDEUE."
            )


def validate_optional_email(value: Any, *, fallback_member_id: str) -> str:
    """Normalize optional family allowlist email (or derive a safe local family email fallback)."""
    raw = str(value or "").strip()
    if not raw:
        safe_slug = re.sub(r"[^a-z0-9._-]+", "", fallback_member_id.lower()) or "member"
        return f"{safe_slug}@carmichael-family.local"
    norm = normalize_email(raw)
    if _RAW_SSN_RE.search(norm):
        raise OnboardingValidationError("ADR-011 violation: SSN patterns are strictly prohibited.")
    if not _EMAIL_BASIC_RE.fullmatch(norm):
        raise OnboardingValidationError(f"Invalid family email address '{raw}'.")
    return norm


class MemberOnboardingService:
    """Persistent 5-stage member onboarding coordinator synchronized across DB, Ledger, and Lineage."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        db_engine: Any = default_engine,
        lineage_service: Optional[LineageHierarchyService] = None,
        capital_ledger: Optional[CapitalLedger] = None,
    ) -> None:
        self._session_factory = session_factory
        self._engine = db_engine
        self._lineage = lineage_service or get_lineage_service()
        self._ledger = capital_ledger
        Base.metadata.create_all(bind=self._engine)

    def _get_ledger(self) -> Optional[CapitalLedger]:
        if self._ledger is not None:
            return self._ledger
        try:
            from app.api.v1.portal_router import _GLOBAL_LEDGER

            return _GLOBAL_LEDGER
        except Exception:
            return None

    def _normalize_single_payload(
        self,
        raw: Dict[str, Any],
        *,
        from_csv: bool = False,
    ) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            raise OnboardingValidationError("Member payload must be a JSON object.")
        reject_forbidden_banking_fields(raw)

        full_name = str(raw.get("full_name") or "").strip()
        if len(full_name) < 2 or len(full_name) > 120:
            raise OnboardingValidationError("full_name must be between 2 and 120 characters.")

        raw_member_id = str(raw.get("member_id") or "").strip()
        if raw_member_id:
            if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", raw_member_id):
                raise OnboardingValidationError(
                    "member_id may contain only letters, digits, '.', '_', or '-' (3–64 chars)."
                )
            member_id = raw_member_id
        else:
            member_id = f"MEM-{_slugify_name(full_name)}-{uuid.uuid4().hex[:6].upper()}"

        email = validate_optional_email(
            raw.get("email") if raw.get("email") is not None else raw.get("applicant_email"),
            fallback_member_id=member_id,
        )

        house_input = raw.get("lineage_house")
        if house_input is None:
            house_input = raw.get("house_id")
        house_id, lineage_code = validate_lineage_house(house_input)

        role_tier = validate_role_tier(raw.get("role_tier") or "MEMBER_USER")

        if "seed_cents" not in raw:
            raise OnboardingValidationError(
                "ADR-008 violation: seed_cents (exact integer cents) is required."
            )
        seed_cents = validate_exact_cents(raw["seed_cents"], allow_integer_string=from_csv)

        risk_dial_bps = validate_risk_dial_bps(
            risk_dial_pct=raw.get("risk_dial_pct"),
            risk_dial_bps=raw.get("risk_dial_bps"),
        )
        is_custodial = _parse_bool_strict(raw.get("is_custodial", False))
        bank_ref_token = validate_opaque_bank_ref(raw.get("bank_ref_token"))

        scma_id = str(raw.get("scma_id") or "").strip()
        if scma_id:
            if not re.fullmatch(r"SCMA-[A-Z0-9_-]{3,48}", scma_id):
                raise OnboardingValidationError("scma_id must start with 'SCMA-' and contain uppercase alphanumeric/dash/underscore characters.")
        else:
            scma_id = f"SCMA-{_slugify_name(full_name)}-{uuid.uuid4().hex[:8].upper()}"

        return {
            "member_id": member_id,
            "scma_id": scma_id,
            "full_name": full_name,
            "email": email,
            "house_id": house_id,
            "lineage_code": lineage_code,
            "role_tier": role_tier,
            "seed_cents": seed_cents,
            "high_water_mark_cents": seed_cents,  # ADR-012: HWM initialized to exact seed
            "risk_dial_bps": risk_dial_bps,
            "is_custodial": is_custodial,
            "bank_ref_token": bank_ref_token,
        }

    def _serialize_member(self, row: OnboardingMemberModel) -> Dict[str, Any]:
        resolved_email = (row.email or "").strip() or validate_optional_email(
            None, fallback_member_id=row.member_id
        )
        return {
            "member_id": row.member_id,
            "scma_id": row.scma_id,
            "full_name": row.full_name,
            "email": resolved_email,
            "house_id": int(row.house_id),
            "lineage_code": row.lineage_code,
            "role_tier": row.role_tier,
            "seed_cents": int(row.seed_cents),
            "balance_cents": int(row.seed_cents),
            "high_water_mark_cents": int(row.high_water_mark_cents),
            "risk_dial_bps": int(row.risk_dial_bps),
            "risk_dial_pct": round(int(row.risk_dial_bps) / 100.0, 2),
            "is_custodial": bool(row.is_custodial),
            "bank_ref_token": row.bank_ref_token,
            "status": row.status,
            "certification_level": row.certification_level,
            "certified_at": row.certified_at,
            "invite_activated_at": row.invite_activated_at,
            "requires_orientation": row.status == STATUS_PENDING_CERT,
            "ifas_portal_host": IFAS_PORTAL_HOST,
            "created_by": row.created_by,
            "created_at": row.created_at,
        }

    def _sync_member_to_runtime(self, normalized: Dict[str, Any]) -> None:
        self._lineage.register_onboarded_member(
            house_id=normalized["house_id"],
            scma_id=normalized["scma_id"],
            member_id=normalized["member_id"],
            name=normalized["full_name"],
            role_tier=normalized["role_tier"],
            seed_cents=normalized["seed_cents"],
            risk_dial_bps=normalized["risk_dial_bps"],
            is_custodial=normalized["is_custodial"],
            bank_ref_token=normalized["bank_ref_token"],
            status=STATUS_PENDING_CERT,
        )
        ledger = self._get_ledger()
        if ledger is not None:
            ledger.register_member_account(
                member_id=normalized["scma_id"],
                seed_capital_cents=normalized["seed_cents"],
                max_risk_pct=normalized["risk_dial_bps"] / 10_000.0,
            )

    def _persist_member_and_invite(
        self,
        db: Session,
        normalized: Dict[str, Any],
        *,
        created_by: str,
        now_dt: datetime,
    ) -> Dict[str, Any]:
        if db.get(OnboardingMemberModel, normalized["member_id"]) is not None:
            raise OnboardingValidationError(
                f"member_id '{normalized['member_id']}' is already provisioned.",
                status_code=409,
            )
        dup_scma = (
            db.query(OnboardingMemberModel)
            .filter(OnboardingMemberModel.scma_id == normalized["scma_id"])
            .first()
        )
        if dup_scma is not None:
            raise OnboardingValidationError(
                f"scma_id '{normalized['scma_id']}' is already provisioned.",
                status_code=409,
            )

        now_iso = now_dt.isoformat()
        expires_iso = (now_dt + timedelta(hours=INVITE_TTL_HOURS)).isoformat()
        raw_token = f"pdeue_inv_{secrets.token_urlsafe(32)}"
        token_hash = _hash_token(raw_token)

        member_row = OnboardingMemberModel(
            member_id=normalized["member_id"],
            scma_id=normalized["scma_id"],
            full_name=normalized["full_name"],
            email=normalized["email"],
            house_id=normalized["house_id"],
            lineage_code=normalized["lineage_code"],
            role_tier=normalized["role_tier"],
            seed_cents=normalized["seed_cents"],
            high_water_mark_cents=normalized["seed_cents"],
            risk_dial_bps=normalized["risk_dial_bps"],
            is_custodial=1 if normalized["is_custodial"] else 0,
            bank_ref_token=normalized["bank_ref_token"],
            status=STATUS_PENDING_CERT,
            certification_level=None,
            certified_at=None,
            invite_activated_at=None,
            created_by=created_by,
            created_at=now_iso,
        )
        db.add(member_row)

        # Mirror into canonical UserModel and AccountModel (ADR-008 + ADR-012 HWM)
        if db.get(UserModel, normalized["member_id"]) is None:
            db.add(
                UserModel(
                    user_id=normalized["member_id"],
                    tenant_id=normalized["lineage_code"],
                    username=normalized["full_name"],
                    email=normalized["email"],
                    role=normalized["role_tier"],
                    created_at=now_iso,
                )
            )
        if db.get(AccountModel, normalized["scma_id"]) is None:
            db.add(
                AccountModel(
                    account_id=normalized["scma_id"],
                    user_id=normalized["member_id"],
                    tenant_id=normalized["lineage_code"],
                    account_name=f"{normalized['full_name']} SCMA",
                    balance_cents=normalized["seed_cents"],
                    high_water_mark_cents=normalized["seed_cents"],
                    currency="USD",
                    status=STATUS_PENDING_CERT,
                    created_at=now_iso,
                )
            )

        invite_row = OnboardingInviteTokenModel(
            token_hash=token_hash,
            token_prefix=raw_token[:16],
            member_id=normalized["member_id"],
            scma_id=normalized["scma_id"],
            expires_at=expires_iso,
            consumed_at=None,
            created_at=now_iso,
        )
        db.add(invite_row)

        self._record_audit(
            db,
            tenant_id=normalized["lineage_code"],
            actor_id=created_by,
            action="MEMBER_PROVISIONED",
            payload={
                "member_id": normalized["member_id"],
                "scma_id": normalized["scma_id"],
                "lineage_code": normalized["lineage_code"],
                "role_tier": normalized["role_tier"],
                "seed_cents": normalized["seed_cents"],
                "high_water_mark_cents": normalized["seed_cents"],
                "risk_dial_bps": normalized["risk_dial_bps"],
                "is_custodial": normalized["is_custodial"],
                "bank_ref_token": normalized["bank_ref_token"],
                "status": STATUS_PENDING_CERT,
                "invite_expires_at": expires_iso,
            },
            recorded_at=now_iso,
        )

        return {
            "status": "PROVISIONED",
            "member": self._serialize_member(member_row),
            "invite": {
                "token": raw_token,
                "activation_link": f"/member?scma_id={normalized['scma_id']}&invite_token={raw_token}",
                "activate_portal_url": f"/activate?token={raw_token}",
                "expires_at": expires_iso,
                "ttl_hours": INVITE_TTL_HOURS,
                "single_use": True,
            },
        }

    def _record_audit(
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
        entry_id = f"AUD-ONB-{uuid.uuid4().hex[:12].upper()}"
        prev_hash = "0" * 64
        digest = hashlib.sha256(f"{prev_hash}|{tenant_id}|{actor_id}|{action}|{payload_str}".encode("utf-8")).hexdigest()
        db.add(
            AuditLogRecordModel(
                entry_id=entry_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                action=action,
                prev_hash=prev_hash,
                entry_hash=digest,
                payload=payload_str,
                recorded_at=recorded_at,
            )
        )

    def provision_member(
        self,
        payload: Dict[str, Any],
        *,
        created_by: str = "CHIEF_ADMINISTRATOR",
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Stage 1: Provision a single member and issue a 48h single-use invite token."""
        normalized = self._normalize_single_payload(payload, from_csv=False)
        now_dt = _utc_now(now)
        db = self._session_factory()
        try:
            receipt = self._persist_member_and_invite(
                db, normalized, created_by=created_by, now_dt=now_dt
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        self._sync_member_to_runtime(normalized)
        return receipt

    def parse_csv_rows(self, csv_text: str) -> List[Dict[str, Any]]:
        """Parse CSV batch text into row dictionaries with fail-closed header validation."""
        cleaned = (csv_text or "").strip()
        if not cleaned:
            raise OnboardingValidationError("CSV batch input is empty.")
        reader = csv.DictReader(io.StringIO(cleaned))
        if not reader.fieldnames:
            raise OnboardingValidationError("CSV batch input is missing a header row.")
        rows: List[Dict[str, Any]] = []
        for raw_row in reader:
            if not any((v or "").strip() for v in raw_row.values()):
                continue
            normalized_row = {
                str(k).strip(): (v.strip() if isinstance(v, str) else v)
                for k, v in raw_row.items()
                if k is not None
            }
            rows.append(normalized_row)
        if not rows:
            raise OnboardingValidationError("CSV batch input contains no member data rows.")
        return rows

    def provision_batch(
        self,
        records: List[Dict[str, Any]],
        *,
        from_csv: bool = False,
        created_by: str = "CHIEF_ADMINISTRATOR",
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Stage 1 Batch Provisioning (JSON or CSV).
        Atomic fail-closed: validates every row before committing any member.
        """
        if not isinstance(records, list) or len(records) == 0:
            raise OnboardingValidationError("Batch payload must contain at least one member record.")
        if len(records) > 250:
            raise OnboardingValidationError("Batch size cannot exceed 250 members per request.")

        normalized_rows: List[Dict[str, Any]] = []
        seen_member_ids = set()
        seen_scma_ids = set()
        for idx, rec in enumerate(records, start=1):
            try:
                norm = self._normalize_single_payload(rec, from_csv=from_csv)
            except OnboardingValidationError as exc:
                raise OnboardingValidationError(f"Row {idx}: {exc}", status_code=exc.status_code) from exc
            if norm["member_id"] in seen_member_ids:
                raise OnboardingValidationError(f"Row {idx}: duplicate member_id '{norm['member_id']}' in batch.")
            if norm["scma_id"] in seen_scma_ids:
                raise OnboardingValidationError(f"Row {idx}: duplicate scma_id '{norm['scma_id']}' in batch.")
            seen_member_ids.add(norm["member_id"])
            seen_scma_ids.add(norm["scma_id"])
            normalized_rows.append(norm)

        now_dt = _utc_now(now)
        receipts: List[Dict[str, Any]] = []
        db = self._session_factory()
        try:
            for norm in normalized_rows:
                receipts.append(
                    self._persist_member_and_invite(
                        db, norm, created_by=created_by, now_dt=now_dt
                    )
                )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        for norm in normalized_rows:
            self._sync_member_to_runtime(norm)

        return {
            "status": "BATCH_PROVISIONED",
            "count": len(receipts),
            "provisioned": receipts,
        }

    def preview_invite_token(
        self,
        raw_token: str,
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Read-only Stage 2 preview for /activate portal (never consumes the token, zero bank PII)."""
        token_clean = (raw_token or "").strip()
        if not token_clean:
            raise InviteTokenError("Activation token is required.", status_code=400, code="MISSING_TOKEN")

        token_hash = _hash_token(token_clean)
        now_dt = _utc_now(now)

        db = self._session_factory()
        try:
            invite = db.get(OnboardingInviteTokenModel, token_hash)
            if invite is None:
                raise InviteTokenError(
                    "Invalid activation token: this invite link was not recognized.",
                    status_code=404,
                    code="TOKEN_NOT_FOUND",
                )
            if invite.consumed_at is not None:
                raise InviteTokenError(
                    "Activation token has already been used (single-use policy enforced).",
                    status_code=410,
                    code="TOKEN_ALREADY_USED",
                )
            expires_dt = datetime.fromisoformat(invite.expires_at)
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            if now_dt > expires_dt:
                raise InviteTokenError(
                    "Activation token has expired (48-hour activation window exceeded).",
                    status_code=410,
                    code="TOKEN_EXPIRED",
                )
            member = db.get(OnboardingMemberModel, invite.member_id)
            if member is None:
                raise InviteTokenError(
                    "Associated member record not found for token.",
                    status_code=404,
                    code="MEMBER_NOT_FOUND",
                )
            serialized = self._serialize_member(member)
            return {
                "valid": True,
                "full_name": serialized["full_name"],
                "email": serialized["email"],
                "house_id": serialized["house_id"],
                "lineage_code": serialized["lineage_code"],
                "role_tier": serialized["role_tier"],
                "is_custodial": serialized["is_custodial"],
                "status": serialized["status"],
                "expires_at": invite.expires_at,
                "paper_mode": True,
                "gate_g1_status": "HOLD_OBSERVATIONS_ONLY",
                "ifas_portal_host": IFAS_PORTAL_HOST,
            }
        finally:
            db.close()

    def activate_invite_token(
        self,
        raw_token: str,
        *,
        email: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Stage 2: Validate and consume a single-use 48-hour invite activation token.
        Fails closed on unknown, expired, or already-consumed tokens.
        Automatically provisions (or upserts) the member's active AuthUserModel on PR #98's
        private family allowlist (`authorized_hats=["CLASS_M"]`, `is_apex_tier3=False`).
        """
        token_clean = (raw_token or "").strip()
        if not token_clean:
            raise InviteTokenError("Activation token is required.", status_code=400, code="MISSING_TOKEN")

        token_hash = _hash_token(token_clean)
        now_dt = _utc_now(now)
        now_iso = now_dt.isoformat()

        db = self._session_factory()
        try:
            invite = db.get(OnboardingInviteTokenModel, token_hash)
            if invite is None:
                raise InviteTokenError(
                    "Invalid activation token: token does not exist.",
                    status_code=404,
                    code="TOKEN_NOT_FOUND",
                )
            if invite.consumed_at is not None:
                raise InviteTokenError(
                    "Activation token has already been used (single-use policy enforced).",
                    status_code=410,
                    code="TOKEN_ALREADY_USED",
                )
            expires_dt = datetime.fromisoformat(invite.expires_at)
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            if now_dt > expires_dt:
                raise InviteTokenError(
                    "Activation token has expired (48-hour activation window exceeded).",
                    status_code=410,
                    code="TOKEN_EXPIRED",
                )

            member = db.get(OnboardingMemberModel, invite.member_id)
            if member is None:
                raise InviteTokenError(
                    "Associated member record not found for token.",
                    status_code=404,
                    code="MEMBER_NOT_FOUND",
                )

            if email is not None and str(email).strip():
                try:
                    resolved_email = validate_optional_email(email, fallback_member_id=member.member_id)
                except OnboardingValidationError as exc:
                    raise InviteTokenError(str(exc), status_code=422, code="INVALID_EMAIL") from exc
                member.email = resolved_email
                user_mirror = db.get(UserModel, member.member_id)
                if user_mirror is not None:
                    user_mirror.email = resolved_email
            else:
                resolved_email = (member.email or "").strip() or validate_optional_email(
                    None, fallback_member_id=member.member_id
                )
                if not member.email:
                    member.email = resolved_email

            invite.consumed_at = now_iso
            member.invite_activated_at = now_iso

            auth_allowlist_user = provision_member_auth_allowlist_in_session(
                db,
                user_id=member.member_id,
                email=resolved_email,
                display_name=member.full_name,
                scma_id=member.scma_id,
                house_id=member.lineage_code,
                actor_id=member.member_id,
                source="INVITE_ACTIVATION",
            )

            self._record_audit(
                db,
                tenant_id=member.lineage_code,
                actor_id=member.member_id,
                action="INVITE_TOKEN_ACTIVATED",
                payload={
                    "member_id": member.member_id,
                    "scma_id": member.scma_id,
                    "token_prefix": invite.token_prefix,
                    "activated_at": now_iso,
                    "auth_allowlist_provisioned": True,
                    "authorized_hats": auth_allowlist_user["authorized_hats"],
                    "is_apex_tier3": False,
                },
                recorded_at=now_iso,
            )
            db.commit()
            serialized = self._serialize_member(member)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        self._lineage.mark_member_activated(serialized["scma_id"], now_iso)
        return {
            "status": "ACTIVATED_PENDING_CERTIFICATION",
            "member_status": serialized["status"],
            "default_view": "orientation",
            "redirect_url": f"/member?scma_id={serialized['scma_id']}",
            "companion_url": f"/companion?scma_id={serialized['scma_id']}&chapter=6",
            "login_url": "/login",
            "member": serialized,
            "auth_allowlist_user": auth_allowlist_user,
        }

    def certify_member(
        self,
        *,
        scma_id: Optional[str] = None,
        member_id: Optional[str] = None,
        chapter_completed: int = 6,
        quiz_passed: bool = False,
        correct_answers: int = 0,
        total_questions: int = 3,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Stage 4: Upgrade a PENDING_TUTOR_CERTIFICATION member to ACTIVE (STEWARDSHIP_L1_CERTIFIED)
        upon passing the Chapter 6 comprehension self-check on /companion.
        """
        if not scma_id and not member_id:
            raise OnboardingValidationError("Either scma_id or member_id is required for certification.")
        if int(chapter_completed) < 6:
            raise OnboardingValidationError(
                "Certification requires completing Chapter 6 (Sovereign Governance & Self-Check).",
                status_code=400,
            )
        if not quiz_passed or int(total_questions) < 3 or int(correct_answers) < int(total_questions):
            raise OnboardingValidationError(
                "Certification requires 100% pass on the Chapter 6 comprehension self-check.",
                status_code=400,
            )

        now_iso = _utc_now(now).isoformat()
        db = self._session_factory()
        try:
            member: Optional[OnboardingMemberModel] = None
            if scma_id:
                member = (
                    db.query(OnboardingMemberModel)
                    .filter(OnboardingMemberModel.scma_id == scma_id.strip())
                    .first()
                )
            if member is None and member_id:
                member = db.get(OnboardingMemberModel, member_id.strip())

            if member is not None:
                member.status = STATUS_ACTIVE
                member.certification_level = CERTIFICATION_LEVEL_L1
                member.certified_at = now_iso

                acct = db.get(AccountModel, member.scma_id)
                if acct is not None:
                    acct.status = STATUS_ACTIVE

                self._record_audit(
                    db,
                    tenant_id=member.lineage_code,
                    actor_id=member.member_id,
                    action=CERTIFICATION_LEVEL_L1,
                    payload={
                        "member_id": member.member_id,
                        "scma_id": member.scma_id,
                        "chapter_completed": int(chapter_completed),
                        "correct_answers": int(correct_answers),
                        "total_questions": int(total_questions),
                        "certified_at": now_iso,
                    },
                    recorded_at=now_iso,
                )
                db.commit()
                serialized = self._serialize_member(member)
                try:
                    self._lineage.certify_member(
                        member.scma_id,
                        certification_level=CERTIFICATION_LEVEL_L1,
                        certified_at=now_iso,
                    )
                except ValueError:
                    pass
                return {
                    "status": "CERTIFIED",
                    "member_id": serialized["member_id"],
                    "scma_id": serialized["scma_id"],
                    "member_status": STATUS_ACTIVE,
                    "certification_level": CERTIFICATION_LEVEL_L1,
                    "certified_at": now_iso,
                    "member": serialized,
                }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # Fallback for pre-seeded canonical lineage members (e.g. Eleanor Vance) completing /companion
        if scma_id:
            try:
                updated = self._lineage.certify_member(
                    scma_id.strip(),
                    certification_level=CERTIFICATION_LEVEL_L1,
                    certified_at=now_iso,
                )
                return {
                    "status": "CERTIFIED",
                    "member_id": updated.get("member_id") or f"USR-{updated['scma_id']}",
                    "scma_id": updated["scma_id"],
                    "member_status": STATUS_ACTIVE,
                    "certification_level": CERTIFICATION_LEVEL_L1,
                    "certified_at": now_iso,
                    "member": {
                        "scma_id": updated["scma_id"],
                        "full_name": updated["name"],
                        "status": STATUS_ACTIVE,
                        "certification_level": CERTIFICATION_LEVEL_L1,
                        "certified_at": now_iso,
                    },
                }
            except ValueError as exc:
                raise OnboardingValidationError(str(exc), status_code=404) from exc

        raise OnboardingValidationError("Member not found for certification.", status_code=404)

    def get_member_by_scma(self, scma_id: str) -> Optional[Dict[str, Any]]:
        db = self._session_factory()
        try:
            row = (
                db.query(OnboardingMemberModel)
                .filter(OnboardingMemberModel.scma_id == scma_id)
                .first()
            )
            return self._serialize_member(row) if row is not None else None
        finally:
            db.close()

    def list_members(self) -> List[Dict[str, Any]]:
        db = self._session_factory()
        try:
            rows = (
                db.query(OnboardingMemberModel)
                .order_by(OnboardingMemberModel.created_at.desc())
                .all()
            )
            return [self._serialize_member(r) for r in rows]
        finally:
            db.close()


_onboarding_service: Optional[MemberOnboardingService] = None


def get_onboarding_service() -> MemberOnboardingService:
    global _onboarding_service
    if _onboarding_service is None:
        _onboarding_service = MemberOnboardingService()
    return _onboarding_service
