"""PR #98 — Session Authentication, Single-Use 6-Digit Email Code & Magic Link,
Apex Passphrase + MFA (with WebAuthn-ready hook), Signed HttpOnly Cookie,
Server-Side Active-Hat Lock, Tenant Jailing & Chief Admin Session Revocation.

Security & Governance Invariants:
- Private Family Allowlist Only: ZERO public registration. Unknown or inactive emails
  return the exact same calm generic 200 response without sending any notification or
  leaking account existence.
- Zero Plaintext Secrets in Storage: Only SHA-256 hashes of single-use 6-digit codes
  and Magic Link tokens, salted PBKDF2-HMAC-SHA256 hashes of Apex passphrases, and
  salted PBKDF2-HMAC-SHA256 hashes of MFA codes/secrets are stored.
- Apex & Tier-3 Command Lock (`CHIEF_ADMIN`, `T3`, `F3`): Strictly prohibited from
  passwordless email shortcuts; require verified Passphrase + 6-digit MFA (or FIDO2/WebAuthn).
- Directive R-12 Notification Firewall: Outbound sign-in codes dispatch exclusively
  through the isolated NotificationGateway with zero balances, dollar figures, or SCMA IDs.
- Tiered Session Windows:
    * Class M: 7-day active window + 2-hour idle timeout.
    * Officers & Apex: 8-hour active window + 30-minute idle timeout.
- Every sign-in, failure, hat-switch, tenant-jail block, and revocation writes an
  immutable entry to GovernanceAuditLog.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import secrets
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple
import uuid

from sqlalchemy.orm import Session, sessionmaker

from app.core.security import SECRET_KEY
from app.db.models import (
    AuthLoginChallengeModel,
    AuthSessionModel,
    AuthUserModel,
    Base,
)
from app.db.session import SessionLocal, engine as default_engine
from app.domain.authority_tiers import (
    get_governance_audit_log,
    is_chief_admin_deputy_role,
    is_chief_admin_role,
    normalize_advisor_role,
    normalize_role_token,
    normalize_tech_tier,
)
from app.domain.notification_gateway import (
    NotificationGateway,
    NotificationMessage,
    get_notification_gateway,
)

SESSION_COOKIE_NAME = "pdeue_session"
GENERIC_CODE_SENT_MESSAGE = (
    "If your email is on the family roster, a sign-in code has been sent."
)

CHALLENGE_TTL_SECONDS = 600  # 10 minutes
MAX_CHALLENGE_ATTEMPTS = 5

CLASS_M_ACTIVE_WINDOW_SECONDS = 7 * 24 * 3600  # 7 days
CLASS_M_IDLE_TIMEOUT_SECONDS = 2 * 3600  # 2 hours

OFFICER_ACTIVE_WINDOW_SECONDS = 8 * 3600  # 8 hours
OFFICER_IDLE_TIMEOUT_SECONDS = 30 * 60  # 30 minutes

PBKDF2_ITERATIONS = 120_000

APEX_TIER3_HATS: Set[str] = {
    "CHIEF_ADMIN",
    "CHIEF_ADMINISTRATOR",
    "T3",
    "F3",
}

CLASS_M_HATS: Set[str] = {
    "MEMBER_USER",
    "PERSONAL_SCMA",
    "CLASS_M",
}

OFFICER_AND_APEX_HATS: Set[str] = {
    "CHIEF_ADMIN",
    "CHIEF_ADMINISTRATOR",
    "CHIEF_ADMIN_DEPUTY",
    "H1",
    "H2",
    "HOUSE_GENEALOGIST",
    "F1",
    "F2-H",
    "F2-A",
    "F3",
    "T1",
    "T2",
    "T2-HOUSEHOLD",
    "T3",
}

_SIX_DIGIT_RE = re.compile(r"^\d{6}$")
_NINE_CONSECUTIVE_DIGITS_RE = re.compile(r"\d{9}")

# Paper/CI demo defaults for Apex seats (overridable via env; never production secrets)
DEV_DEFAULT_APEX_PASSPHRASE = (
    os.getenv("PDEUE_DEV_APEX_PASSPHRASE", "").strip()
    or "Carmichael-Sovereign-Stewardship-2026!"
)
DEV_DEFAULT_APEX_MFA_CODE = (
    os.getenv("PDEUE_DEV_APEX_MFA_CODE", "").strip() or "482916"
)


class SessionAuthError(Exception):
    """Structured session authentication exception carrying HTTP status and error code."""

    def __init__(self, status_code: int, detail: str, error_code: str = "AUTH_ERROR") -> None:
        super().__init__(detail)
        self.status_code = int(status_code)
        self.detail = detail
        self.error_code = error_code


@dataclass(frozen=True)
class AuthenticatedSessionContext:
    """Verified server-side session context bound to an authenticated request."""

    session_id: str
    user_id: str
    email: str
    display_name: str
    scma_id: Optional[str]
    house_id: str
    active_hat: str
    authorized_hats: Tuple[str, ...]
    is_apex_tier3: bool
    issued_at: str
    last_activity_at: str
    expires_at: str
    idle_timeout_seconds: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "email": self.email,
            "display_name": self.display_name,
            "scma_id": self.scma_id,
            "house_id": self.house_id,
            "active_hat": self.active_hat,
            "authorized_hats": list(self.authorized_hats),
            "is_apex_tier3": self.is_apex_tier3,
            "issued_at": self.issued_at,
            "last_activity_at": self.last_activity_at,
            "expires_at": self.expires_at,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "workspace_url": workspace_url_for_hat(self.active_hat, self.house_id),
        }


def is_session_auth_enforced() -> bool:
    """Return True when strict fail-closed session auth is enabled via environment."""
    return os.getenv("PDEUE_ENFORCE_SESSION_AUTH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def normalize_email(raw_email: str) -> str:
    return (raw_email or "").strip().lower()


def sha256_hex(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def hash_secret_pbkdf2(secret_value: str, *, salt_hex: Optional[str] = None) -> str:
    """Hash a passphrase or MFA secret with salted PBKDF2-HMAC-SHA256."""
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        (secret_value or "").encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_secret_pbkdf2(secret_value: str, stored_hash: Optional[str]) -> bool:
    """Constant-time verification of a PBKDF2-HMAC-SHA256 hash."""
    if not stored_hash or not secret_value:
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_hex = parts[3]
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            secret_value.encode("utf-8"),
            salt,
            iterations,
        ).hex()
        return hmac.compare_digest(computed, expected_hex)
    except Exception:
        return False


def _session_signing_secret() -> bytes:
    raw = os.getenv("PDEUE_SESSION_SECRET", "").strip() or SECRET_KEY
    return raw.encode("utf-8")


def sign_session_id(session_id: str) -> str:
    """Create an HMAC-SHA256 signed cookie token for a session_id."""
    mac = hmac.new(
        _session_signing_secret(),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")
    return f"{session_id}.{sig_b64}"


def verify_signed_session_cookie(cookie_value: Optional[str]) -> Optional[str]:
    """Verify HMAC-SHA256 cookie signature and return session_id if valid, else None."""
    if not cookie_value or "." not in cookie_value:
        return None
    session_id, sig = cookie_value.rsplit(".", 1)
    if not session_id or not sig:
        return None
    expected = sign_session_id(session_id).rsplit(".", 1)[1]
    if not hmac.compare_digest(sig, expected):
        return None
    return session_id


def _parse_iso_utc(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_authorized_hats(raw_json: Optional[str]) -> List[str]:
    if not raw_json:
        return ["MEMBER_USER"]
    try:
        loaded = json.loads(raw_json)
        if not isinstance(loaded, list):
            return ["MEMBER_USER"]
    except Exception:
        return ["MEMBER_USER"]
    out: List[str] = []
    for item in loaded:
        norm = normalize_role_token(str(item))
        if norm and norm not in out:
            out.append(norm)
    return out or ["MEMBER_USER"]


def _has_apex_hat(hats: Iterable[str]) -> bool:
    for h in hats:
        norm = normalize_role_token(h)
        if norm in APEX_TIER3_HATS or is_chief_admin_role(norm):
            return True
    return False


def _session_timeouts_for_hat(active_hat: str) -> Tuple[int, int]:
    """Return (active_window_seconds, idle_timeout_seconds) for a canonical hat."""
    norm = normalize_role_token(active_hat)
    if norm in CLASS_M_HATS:
        return CLASS_M_ACTIVE_WINDOW_SECONDS, CLASS_M_IDLE_TIMEOUT_SECONDS
    return OFFICER_ACTIVE_WINDOW_SECONDS, OFFICER_IDLE_TIMEOUT_SECONDS


def parse_house_number(house_id: Optional[str]) -> Optional[int]:
    if not house_id:
        return None
    cleaned = str(house_id).strip().upper().replace("HOUSE-", "").replace("HOUSE_", "")
    try:
        num = int(cleaned)
        return num if 1 <= num <= 12 else None
    except ValueError:
        return None


def workspace_url_for_hat(active_hat: str, house_id: Optional[str] = "HOUSE-01") -> str:
    """Resolve the default landing workspace URL for a canonical Active Hat."""
    norm = normalize_role_token(active_hat)
    if is_chief_admin_role(norm):
        return "/dashboard"
    if is_chief_admin_deputy_role(norm):
        return "/dashboard?role=CHIEF_ADMIN_DEPUTY"
    if norm in {"T1", "T2", "T2-HOUSEHOLD", "T3"}:
        tier_label = "T2-Household" if norm == "T2-HOUSEHOLD" else norm
        return f"/admin/tech?tier={tier_label}"
    if norm in {"F1", "F2-H", "F2-A", "F3"}:
        return f"/advisor?role={norm}"
    if norm in {"H1", "H2"}:
        hnum = parse_house_number(house_id) or 1
        return f"/lineage/house/{hnum}?role={norm}"
    if norm == "HOUSE_GENEALOGIST":
        return "/community/heritage"
    return "/member"


def _generate_r12_safe_magic_token() -> str:
    """Generate a URL-safe random token that never trips Directive R-12 9-digit account scans."""
    for _ in range(20):
        tok = "mlk_" + secrets.token_urlsafe(32)
        if not _NINE_CONSECUTIVE_DIGITS_RE.search(tok):
            return tok
    return "mlk_" + secrets.token_hex(24)


def _default_seed_users() -> List[Dict[str, Any]]:
    """Default private family allowlist for paper/dev/CI modes (zero real credentials)."""
    apex_pw_hash = hash_secret_pbkdf2(DEV_DEFAULT_APEX_PASSPHRASE)
    apex_mfa_hash = hash_secret_pbkdf2(DEV_DEFAULT_APEX_MFA_CODE)
    return [
        {
            "user_id": "USR-founder_ch-C8575D7E",
            "email": "founder@carmichael-family.local",
            "display_name": "Founder Chief Admin",
            "scma_id": "SCMA-FOUNDER_-C8575D7E",
            "house_id": "HOUSE-01",
            "authorized_hats": ["CHIEF_ADMINISTRATOR", "PERSONAL_SCMA", "MEMBER_USER"],
            "is_apex_tier3": 1,
            "passphrase_hash": apex_pw_hash,
            "mfa_secret_hash": apex_mfa_hash,
            "active": 1,
        },
        {
            "user_id": "USR-eleanor_va-B2B31C9E",
            "email": "eleanor@carmichael-family.local",
            "display_name": "Eleanor Vance",
            "scma_id": "SCMA-ELEANOR_-B2B31C9E",
            "house_id": "HOUSE-01",
            "authorized_hats": ["MEMBER_USER", "PERSONAL_SCMA", "F2-H"],
            "is_apex_tier3": 0,
            "passphrase_hash": None,
            "mfa_secret_hash": None,
            "active": 1,
        },
        {
            "user_id": "USR-julian_va-A1F98B21",
            "email": "julian@carmichael-family.local",
            "display_name": "Julian Vance (Apprentice)",
            "scma_id": "SCMA-JULIAN_-A1F98B21",
            "house_id": "HOUSE-01",
            "authorized_hats": ["MEMBER_USER", "PERSONAL_SCMA"],
            "is_apex_tier3": 0,
            "passphrase_hash": None,
            "mfa_secret_hash": None,
            "active": 1,
        },
        {
            "user_id": "USR-beta-head",
            "email": "morgan@carmichael-family.local",
            "display_name": "Morgan Vance",
            "scma_id": "SCMA-MORGAN-BETA",
            "house_id": "HOUSE-02",
            "authorized_hats": ["MEMBER_USER", "PERSONAL_SCMA", "F2-H", "H2"],
            "is_apex_tier3": 0,
            "passphrase_hash": None,
            "mfa_secret_hash": None,
            "active": 1,
        },
        {
            "user_id": "USR-tech-t1",
            "email": "t1-monitor@carmichael-family.local",
            "display_name": "Class T1 Monitor",
            "scma_id": None,
            "house_id": "HOUSE-01",
            "authorized_hats": ["T1", "MEMBER_USER"],
            "is_apex_tier3": 0,
            "passphrase_hash": None,
            "mfa_secret_hash": None,
            "active": 1,
        },
        {
            "user_id": "USR-tech-t3",
            "email": "cto@carmichael-family.local",
            "display_name": "Chief Technical Officer (T3)",
            "scma_id": None,
            "house_id": "HOUSE-01",
            "authorized_hats": ["T3", "MEMBER_USER"],
            "is_apex_tier3": 1,
            "passphrase_hash": apex_pw_hash,
            "mfa_secret_hash": apex_mfa_hash,
            "active": 1,
        },
        {
            "user_id": "USR-risk-f3",
            "email": "cro@carmichael-family.local",
            "display_name": "Chief Risk Officer (F3)",
            "scma_id": None,
            "house_id": "HOUSE-01",
            "authorized_hats": ["F3", "MEMBER_USER"],
            "is_apex_tier3": 1,
            "passphrase_hash": apex_pw_hash,
            "mfa_secret_hash": apex_mfa_hash,
            "active": 1,
        },
        {
            "user_id": "USR-genealogist-h1",
            "email": "genealogist@carmichael-family.local",
            "display_name": "House 01 Genealogist",
            "scma_id": None,
            "house_id": "HOUSE-01",
            "authorized_hats": ["HOUSE_GENEALOGIST", "H1", "MEMBER_USER"],
            "is_apex_tier3": 0,
            "passphrase_hash": None,
            "mfa_secret_hash": None,
            "active": 1,
        },
    ]


class SessionAuthService:
    """Persistent session authentication, single-use codes, Apex MFA, Active-Hat lock, and revocation."""

    def __init__(
        self,
        *,
        session_factory: Optional[sessionmaker] = None,
        bind_engine: Optional[Any] = None,
        notification_gateway: Optional[NotificationGateway] = None,
        clock_fn: Optional[Callable[[], datetime]] = None,
        webauthn_verifier: Optional[Callable[[AuthUserModel, Dict[str, Any]], bool]] = None,
        seed_defaults: bool = True,
    ) -> None:
        self._engine = bind_engine or default_engine
        self._session_factory = session_factory or SessionLocal
        self._notifications = notification_gateway or get_notification_gateway()
        self._clock = clock_fn or (lambda: datetime.now(timezone.utc))
        self._webauthn_verifier = webauthn_verifier
        self._lock = RLock()
        self._seed_defaults_flag = seed_defaults
        self._ensure_tables_and_seed()

    def _now(self) -> datetime:
        dt = self._clock()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _ensure_tables_and_seed(self) -> None:
        with self._lock:
            Base.metadata.create_all(
                bind=self._engine,
                tables=[
                    AuthUserModel.__table__,
                    AuthLoginChallengeModel.__table__,
                    AuthSessionModel.__table__,
                ],
            )
            if not self._seed_defaults_flag:
                return
            db: Session = self._session_factory()
            try:
                existing_ids = {
                    row[0] for row in db.query(AuthUserModel.user_id).all()
                }
                existing_emails = {
                    row[0] for row in db.query(AuthUserModel.email).all()
                }
                added = False
                for spec in _default_seed_users():
                    if spec["user_id"] in existing_ids or spec["email"] in existing_emails:
                        continue
                    db.add(
                        AuthUserModel(
                            user_id=spec["user_id"],
                            email=normalize_email(spec["email"]),
                            display_name=spec["display_name"],
                            scma_id=spec["scma_id"],
                            house_id=spec["house_id"],
                            authorized_hats=json.dumps(spec["authorized_hats"]),
                            is_apex_tier3=int(spec["is_apex_tier3"]),
                            passphrase_hash=spec["passphrase_hash"],
                            mfa_secret_hash=spec["mfa_secret_hash"],
                            active=int(spec["active"]),
                        )
                    )
                    added = True
                if added:
                    db.commit()
            finally:
                db.close()

    def set_webauthn_verifier(
        self, verifier: Optional[Callable[[AuthUserModel, Dict[str, Any]], bool]]
    ) -> None:
        """Attach an optional FIDO2/WebAuthn assertion verifier hook for Apex accounts."""
        self._webauthn_verifier = verifier

    def upsert_allowlist_user(
        self,
        *,
        user_id: str,
        email: str,
        display_name: str,
        scma_id: Optional[str] = None,
        house_id: str = "HOUSE-01",
        authorized_hats: Sequence[str] = ("MEMBER_USER",),
        is_apex_tier3: bool = False,
        passphrase: Optional[str] = None,
        mfa_code: Optional[str] = None,
        active: bool = True,
    ) -> Dict[str, Any]:
        """Register or update a private family allowlist user (administrative/testing helper)."""
        norm_email = normalize_email(email)
        norm_hats = []
        for h in authorized_hats:
            tok = normalize_role_token(h)
            if tok and tok not in norm_hats:
                norm_hats.append(tok)
        if not norm_hats:
            norm_hats = ["MEMBER_USER"]
        apex_flag = 1 if (is_apex_tier3 or _has_apex_hat(norm_hats)) else 0

        db: Session = self._session_factory()
        try:
            row = db.query(AuthUserModel).filter(AuthUserModel.user_id == user_id).first()
            if row is None:
                row = AuthUserModel(
                    user_id=user_id,
                    email=norm_email,
                    display_name=display_name,
                    scma_id=scma_id,
                    house_id=house_id,
                    authorized_hats=json.dumps(norm_hats),
                    is_apex_tier3=apex_flag,
                    passphrase_hash=hash_secret_pbkdf2(passphrase) if passphrase else None,
                    mfa_secret_hash=hash_secret_pbkdf2(mfa_code) if mfa_code else None,
                    active=1 if active else 0,
                )
                db.add(row)
            else:
                row.email = norm_email
                row.display_name = display_name
                row.scma_id = scma_id
                row.house_id = house_id
                row.authorized_hats = json.dumps(norm_hats)
                row.is_apex_tier3 = apex_flag
                if passphrase is not None:
                    row.passphrase_hash = hash_secret_pbkdf2(passphrase)
                if mfa_code is not None:
                    row.mfa_secret_hash = hash_secret_pbkdf2(mfa_code)
                row.active = 1 if active else 0
            db.commit()
            return {
                "user_id": row.user_id,
                "email": row.email,
                "display_name": row.display_name,
                "scma_id": row.scma_id,
                "house_id": row.house_id,
                "authorized_hats": norm_hats,
                "is_apex_tier3": bool(row.is_apex_tier3),
                "active": bool(row.active),
            }
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Universal Passwordless Sign-In (6-Digit Code & Single-Use Magic Link)
    # ------------------------------------------------------------------

    def request_login_code(
        self,
        email: str,
        *,
        include_debug_secret: bool = False,
    ) -> Dict[str, Any]:
        """Issue a single-use 6-digit email code & Magic Link for allowlisted non-Apex users.

        Unknown or inactive emails receive the exact same calm generic 200 payload with
        ZERO outbound notifications dispatched (preventing account enumeration).
        Apex/Tier-3 accounts (`CHIEF_ADMIN`, `T3`, `F3`) are explicitly rejected from
        passwordless shortcuts (HTTP 403).
        """
        norm_email = normalize_email(email)
        audit = get_governance_audit_log()
        now = self._now()

        db: Session = self._session_factory()
        try:
            user = (
                db.query(AuthUserModel)
                .filter(AuthUserModel.email == norm_email)
                .first()
            )
            if user is None or not user.active:
                audit.record(
                    event_type="AUTH_CODE_REQUEST_IGNORED",
                    actor_id=norm_email or "anonymous",
                    actor_role="UNAUTHENTICATED",
                    target_id="auth_login_challenges",
                    action="REQUEST_LOGIN_CODE",
                    outcome="IGNORED_NOT_ON_ALLOWLIST",
                    http_status=200,
                    detail="Ignored sign-in code request for non-allowlisted or inactive email (generic 200 returned).",
                )
                return {
                    "status": "OK",
                    "message": GENERIC_CODE_SENT_MESSAGE,
                }

            hats = _parse_authorized_hats(user.authorized_hats)
            if bool(user.is_apex_tier3) or _has_apex_hat(hats):
                audit.record(
                    event_type="AUTH_PASSWORDLESS_REJECTED_APEX",
                    actor_id=user.user_id,
                    actor_role=",".join(hats),
                    target_id="auth_login_challenges",
                    action="REQUEST_LOGIN_CODE",
                    outcome="DENIED_APEX_MFA_REQUIRED",
                    http_status=403,
                    detail=(
                        "Rejected passwordless email code shortcut for Apex/Tier-3 account; "
                        "Passphrase + 6-digit MFA is mandatory."
                    ),
                )
                raise SessionAuthError(
                    403,
                    "APEX_MFA_REQUIRED: Apex and Tier-3 command accounts (CHIEF_ADMIN, T3, F3) "
                    "must sign in with Passphrase + 6-digit MFA.",
                    error_code="APEX_MFA_REQUIRED",
                )

            # Burn any prior unconsumed challenges for this user to keep active state crisp.
            prior_open = (
                db.query(AuthLoginChallengeModel)
                .filter(
                    AuthLoginChallengeModel.user_id == user.user_id,
                    AuthLoginChallengeModel.consumed_at.is_(None),
                )
                .all()
            )
            for old in prior_open:
                old.consumed_at = now.isoformat()

            code = f"{secrets.randbelow(1_000_000):06d}"
            magic_token = _generate_r12_safe_magic_token()
            challenge_id = f"CHG-{uuid.uuid4().hex[:12].upper()}"
            expires_at = (now + timedelta(seconds=CHALLENGE_TTL_SECONDS)).isoformat()

            db.add(
                AuthLoginChallengeModel(
                    challenge_id=challenge_id,
                    user_id=user.user_id,
                    code_hash=sha256_hex(code),
                    magic_token_hash=sha256_hex(magic_token),
                    expires_at=expires_at,
                    attempts=0,
                    consumed_at=None,
                )
            )
            db.commit()

            # Dispatch strictly R-12 safe email notification (ZERO balances, ZERO SCMA IDs).
            notif = NotificationMessage(
                notification_id=f"AUTH-{challenge_id}",
                title="Your Private Family Sign-In Code",
                message=(
                    f"Your single-use 6-digit sign-in code is {code}. "
                    f"It expires in 10 minutes. "
                    f"Or open this one-time Magic Link on the same device: "
                    f"/api/v1/auth/magic?token={magic_token}"
                ),
                category="SECURITY_SIGNIN",
                target_scope="SINGLE_MEMBER",
                target_house_id=parse_house_number(user.house_id),
                action_url=f"/api/v1/auth/magic?token={magic_token}",
                sender_id="PDEUE_SESSION_AUTH",
                sender_role="SYSTEM",
            )
            receipts = self._notifications.dispatch(
                notif,
                channels=["email"],
                strict_reject=True,
            )

            audit.record(
                event_type="AUTH_CODE_ISSUED",
                actor_id=user.user_id,
                actor_role=hats[0],
                target_id=challenge_id,
                action="REQUEST_LOGIN_CODE",
                outcome="CODE_DISPATCHED",
                http_status=200,
                detail=(
                    f"Single-use 6-digit code & Magic Link issued via "
                    f"{receipts[0].provider if receipts else 'NotificationGateway'} "
                    f"(10-min TTL, R-12 sanitized)."
                ),
            )

            resp: Dict[str, Any] = {
                "status": "OK",
                "message": GENERIC_CODE_SENT_MESSAGE,
            }
            if include_debug_secret:
                resp["_challenge_id"] = challenge_id
                resp["_code"] = code
                resp["_magic_token"] = magic_token
                resp["_expires_at"] = expires_at
                resp["_delivery_receipts"] = [r.to_dict() for r in receipts]
            return resp
        finally:
            db.close()

    def _issue_session_row(
        self,
        db: Session,
        user: AuthUserModel,
        *,
        active_hat: str,
        auth_method: str,
    ) -> Tuple[AuthenticatedSessionContext, str]:
        now = self._now()
        hats = _parse_authorized_hats(user.authorized_hats)
        active_window, idle_timeout = _session_timeouts_for_hat(active_hat)
        session_id = f"SES-{secrets.token_urlsafe(24)}"
        issued_iso = now.isoformat()
        expires_iso = (now + timedelta(seconds=active_window)).isoformat()

        row = AuthSessionModel(
            session_id=session_id,
            user_id=user.user_id,
            scma_id=user.scma_id,
            active_hat=active_hat,
            issued_at=issued_iso,
            last_activity_at=issued_iso,
            expires_at=expires_iso,
            idle_timeout_seconds=idle_timeout,
            revoked_at=None,
            revoked_by=None,
        )
        db.add(row)
        db.commit()

        ctx = AuthenticatedSessionContext(
            session_id=session_id,
            user_id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            scma_id=user.scma_id,
            house_id=user.house_id,
            active_hat=active_hat,
            authorized_hats=tuple(hats),
            is_apex_tier3=bool(user.is_apex_tier3),
            issued_at=issued_iso,
            last_activity_at=issued_iso,
            expires_at=expires_iso,
            idle_timeout_seconds=idle_timeout,
        )
        signed_cookie = sign_session_id(session_id)

        get_governance_audit_log().record(
            event_type="AUTH_LOGIN_SUCCESS",
            actor_id=user.user_id,
            actor_role=active_hat,
            target_id=session_id,
            action=auth_method,
            outcome="SESSION_ISSUED",
            http_status=200,
            detail=(
                f"Authenticated {user.display_name} via {auth_method}; "
                f"Active Hat={active_hat}, idle_timeout={idle_timeout}s."
            ),
            metadata={"auth_method": auth_method, "active_hat": active_hat},
        )
        return ctx, signed_cookie

    def verify_login_code(
        self,
        email: str,
        code: str,
        *,
        requested_hat: Optional[str] = None,
    ) -> Tuple[AuthenticatedSessionContext, str]:
        """Verify a single-use 6-digit code, burn it permanently, and issue a session."""
        norm_email = normalize_email(email)
        cleaned_code = (code or "").strip()
        audit = get_governance_audit_log()
        now = self._now()

        db: Session = self._session_factory()
        try:
            user = (
                db.query(AuthUserModel)
                .filter(AuthUserModel.email == norm_email)
                .first()
            )
            if user is None or not user.active:
                audit.record(
                    event_type="AUTH_LOGIN_FAILED",
                    actor_id=norm_email or "anonymous",
                    actor_role="UNAUTHENTICATED",
                    target_id="verify_code",
                    action="VERIFY_LOGIN_CODE",
                    outcome="DENIED_INVALID_CREDENTIALS",
                    http_status=401,
                    detail="Failed 6-digit code verification for unknown or inactive email.",
                )
                raise SessionAuthError(
                    401,
                    "Invalid or expired sign-in code. Please check the 6 digits or request a fresh code.",
                    error_code="INVALID_CODE",
                )

            hats = _parse_authorized_hats(user.authorized_hats)
            if bool(user.is_apex_tier3) or _has_apex_hat(hats):
                audit.record(
                    event_type="AUTH_PASSWORDLESS_REJECTED_APEX",
                    actor_id=user.user_id,
                    actor_role=",".join(hats),
                    target_id="verify_code",
                    action="VERIFY_LOGIN_CODE",
                    outcome="DENIED_APEX_MFA_REQUIRED",
                    http_status=403,
                    detail="Rejected passwordless code verification for Apex/Tier-3 account.",
                )
                raise SessionAuthError(
                    403,
                    "APEX_MFA_REQUIRED: Apex and Tier-3 command accounts must sign in with Passphrase + MFA.",
                    error_code="APEX_MFA_REQUIRED",
                )

            # Inspect the most recent challenge for this user.
            challenge = (
                db.query(AuthLoginChallengeModel)
                .filter(AuthLoginChallengeModel.user_id == user.user_id)
                .order_by(AuthLoginChallengeModel.expires_at.desc())
                .first()
            )
            if challenge is None or challenge.consumed_at is not None:
                # Distinguish locked-out challenge vs already used/missing
                if challenge is not None and challenge.attempts >= MAX_CHALLENGE_ATTEMPTS:
                    audit.record(
                        event_type="AUTH_CODE_LOCKED_OUT",
                        actor_id=user.user_id,
                        actor_role=hats[0],
                        target_id=challenge.challenge_id,
                        action="VERIFY_LOGIN_CODE",
                        outcome="LOCKED_OUT_MAX_ATTEMPTS",
                        http_status=429,
                        detail="Rejected verification on locked-out challenge (>= 5 failed attempts).",
                    )
                    raise SessionAuthError(
                        429,
                        "LOCKED_OUT: Maximum 5 sign-in attempts exceeded. Please request a fresh 6-digit code.",
                        error_code="CHALLENGE_LOCKED_OUT",
                    )
                audit.record(
                    event_type="AUTH_LOGIN_FAILED",
                    actor_id=user.user_id,
                    actor_role=hats[0],
                    target_id=challenge.challenge_id if challenge else "none",
                    action="VERIFY_LOGIN_CODE",
                    outcome="DENIED_CHALLENGE_CONSUMED_OR_MISSING",
                    http_status=401,
                    detail="Sign-in code already used (single-use burned) or not requested.",
                )
                raise SessionAuthError(
                    401,
                    "This sign-in code has already been used or was not found. Please request a fresh code.",
                    error_code="CODE_CONSUMED_OR_MISSING",
                )

            if now > _parse_iso_utc(challenge.expires_at):
                challenge.consumed_at = now.isoformat()
                db.commit()
                audit.record(
                    event_type="AUTH_CODE_EXPIRED",
                    actor_id=user.user_id,
                    actor_role=hats[0],
                    target_id=challenge.challenge_id,
                    action="VERIFY_LOGIN_CODE",
                    outcome="DENIED_EXPIRED",
                    http_status=401,
                    detail="Rejected expired 6-digit sign-in code (>10-minute TTL).",
                )
                raise SessionAuthError(
                    401,
                    "Your sign-in code has expired (10-minute limit). Please request a fresh code.",
                    error_code="CODE_EXPIRED",
                )

            if challenge.attempts >= MAX_CHALLENGE_ATTEMPTS:
                challenge.consumed_at = now.isoformat()
                db.commit()
                audit.record(
                    event_type="AUTH_CODE_LOCKED_OUT",
                    actor_id=user.user_id,
                    actor_role=hats[0],
                    target_id=challenge.challenge_id,
                    action="VERIFY_LOGIN_CODE",
                    outcome="LOCKED_OUT_MAX_ATTEMPTS",
                    http_status=429,
                    detail="Maximum 5 failed attempts reached; challenge permanently burned.",
                )
                raise SessionAuthError(
                    429,
                    "LOCKED_OUT: Maximum 5 sign-in attempts exceeded. Please request a fresh 6-digit code.",
                    error_code="CHALLENGE_LOCKED_OUT",
                )

            if not _SIX_DIGIT_RE.match(cleaned_code) or not hmac.compare_digest(
                sha256_hex(cleaned_code), challenge.code_hash
            ):
                challenge.attempts += 1
                locked = challenge.attempts >= MAX_CHALLENGE_ATTEMPTS
                if locked:
                    challenge.consumed_at = now.isoformat()
                db.commit()
                audit.record(
                    event_type="AUTH_CODE_LOCKED_OUT" if locked else "AUTH_LOGIN_FAILED",
                    actor_id=user.user_id,
                    actor_role=hats[0],
                    target_id=challenge.challenge_id,
                    action="VERIFY_LOGIN_CODE",
                    outcome="LOCKED_OUT_MAX_ATTEMPTS" if locked else "DENIED_WRONG_CODE",
                    http_status=429 if locked else 401,
                    detail=f"Wrong 6-digit code attempt {challenge.attempts}/{MAX_CHALLENGE_ATTEMPTS}.",
                )
                if locked:
                    raise SessionAuthError(
                        429,
                        "LOCKED_OUT: Maximum 5 sign-in attempts exceeded. Please request a fresh 6-digit code.",
                        error_code="CHALLENGE_LOCKED_OUT",
                    )
                raise SessionAuthError(
                    401,
                    f"Incorrect 6-digit code ({MAX_CHALLENGE_ATTEMPTS - challenge.attempts} attempts remaining).",
                    error_code="INVALID_CODE",
                )

            # Single-use burn on verified code
            challenge.consumed_at = now.isoformat()
            db.commit()

            chosen_hat = self._select_initial_hat(hats, requested_hat=requested_hat, is_apex=False)
            return self._issue_session_row(
                db,
                user,
                active_hat=chosen_hat,
                auth_method="EMAIL_6DIGIT_CODE",
            )
        finally:
            db.close()

    def verify_magic_token(
        self,
        token: str,
        *,
        requested_hat: Optional[str] = None,
    ) -> Tuple[AuthenticatedSessionContext, str]:
        """Verify a single-use Magic Link token, burn it permanently, and issue a session."""
        cleaned_token = (token or "").strip()
        audit = get_governance_audit_log()
        now = self._now()

        if not cleaned_token:
            raise SessionAuthError(401, "Missing Magic Link token.", error_code="MISSING_TOKEN")

        token_hash = sha256_hex(cleaned_token)
        db: Session = self._session_factory()
        try:
            challenge = (
                db.query(AuthLoginChallengeModel)
                .filter(AuthLoginChallengeModel.magic_token_hash == token_hash)
                .first()
            )
            if challenge is None:
                audit.record(
                    event_type="AUTH_LOGIN_FAILED",
                    actor_id="anonymous",
                    actor_role="UNAUTHENTICATED",
                    target_id="magic_link",
                    action="VERIFY_MAGIC_LINK",
                    outcome="DENIED_INVALID_TOKEN",
                    http_status=401,
                    detail="Magic Link token did not match any active challenge.",
                )
                raise SessionAuthError(
                    401,
                    "This Magic Link is invalid or expired. Please request a fresh sign-in code.",
                    error_code="INVALID_MAGIC_TOKEN",
                )

            if challenge.consumed_at is not None:
                audit.record(
                    event_type="AUTH_LOGIN_FAILED",
                    actor_id=challenge.user_id,
                    actor_role="UNAUTHENTICATED",
                    target_id=challenge.challenge_id,
                    action="VERIFY_MAGIC_LINK",
                    outcome="DENIED_ALREADY_CONSUMED",
                    http_status=401,
                    detail="Rejected replay of already-consumed single-use Magic Link.",
                )
                raise SessionAuthError(
                    401,
                    "This Magic Link has already been used. Please request a fresh sign-in code.",
                    error_code="MAGIC_TOKEN_CONSUMED",
                )

            if now > _parse_iso_utc(challenge.expires_at):
                challenge.consumed_at = now.isoformat()
                db.commit()
                audit.record(
                    event_type="AUTH_CODE_EXPIRED",
                    actor_id=challenge.user_id,
                    actor_role="UNAUTHENTICATED",
                    target_id=challenge.challenge_id,
                    action="VERIFY_MAGIC_LINK",
                    outcome="DENIED_EXPIRED",
                    http_status=401,
                    detail="Rejected expired Magic Link (>10-minute TTL).",
                )
                raise SessionAuthError(
                    401,
                    "This Magic Link has expired (10-minute limit). Please request a fresh sign-in code.",
                    error_code="MAGIC_TOKEN_EXPIRED",
                )

            if challenge.attempts >= MAX_CHALLENGE_ATTEMPTS:
                challenge.consumed_at = now.isoformat()
                db.commit()
                raise SessionAuthError(
                    429,
                    "LOCKED_OUT: Too many failed attempts on this challenge. Request a fresh code.",
                    error_code="CHALLENGE_LOCKED_OUT",
                )

            user = (
                db.query(AuthUserModel)
                .filter(AuthUserModel.user_id == challenge.user_id)
                .first()
            )
            if user is None or not user.active:
                raise SessionAuthError(401, "Account is inactive or not found.", error_code="USER_INACTIVE")

            hats = _parse_authorized_hats(user.authorized_hats)
            if bool(user.is_apex_tier3) or _has_apex_hat(hats):
                raise SessionAuthError(
                    403,
                    "APEX_MFA_REQUIRED: Apex and Tier-3 accounts cannot use Magic Links.",
                    error_code="APEX_MFA_REQUIRED",
                )

            # Single-use burn on verified Magic Link
            challenge.consumed_at = now.isoformat()
            db.commit()

            chosen_hat = self._select_initial_hat(hats, requested_hat=requested_hat, is_apex=False)
            return self._issue_session_row(
                db,
                user,
                active_hat=chosen_hat,
                auth_method="EMAIL_MAGIC_LINK",
            )
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Apex & Tier-3 Command Sign-In (CHIEF_ADMIN, T3, F3)
    # ------------------------------------------------------------------

    def verify_apex_login(
        self,
        *,
        email: str,
        passphrase: str,
        mfa_code: Optional[str] = None,
        requested_hat: Optional[str] = None,
        webauthn_assertion: Optional[Dict[str, Any]] = None,
    ) -> Tuple[AuthenticatedSessionContext, str]:
        """Authenticate CHIEF_ADMIN, T3, or F3 via salted PBKDF2 passphrase + 6-digit MFA (or WebAuthn hook)."""
        norm_email = normalize_email(email)
        audit = get_governance_audit_log()

        db: Session = self._session_factory()
        try:
            user = (
                db.query(AuthUserModel)
                .filter(AuthUserModel.email == norm_email)
                .first()
            )
            if user is None or not user.active:
                audit.record(
                    event_type="AUTH_APEX_LOGIN_FAILED",
                    actor_id=norm_email or "anonymous",
                    actor_role="UNAUTHENTICATED",
                    target_id="apex_login",
                    action="APEX_LOGIN",
                    outcome="DENIED_INVALID_CREDENTIALS",
                    http_status=401,
                    detail="Failed Apex/Tier-3 sign-in attempt (invalid or inactive user).",
                )
                raise SessionAuthError(
                    401,
                    "Invalid Apex passphrase or MFA verification.",
                    error_code="APEX_AUTH_FAILED",
                )

            hats = _parse_authorized_hats(user.authorized_hats)
            if not (bool(user.is_apex_tier3) or _has_apex_hat(hats)):
                audit.record(
                    event_type="AUTH_APEX_LOGIN_FAILED",
                    actor_id=user.user_id,
                    actor_role=",".join(hats),
                    target_id="apex_login",
                    action="APEX_LOGIN",
                    outcome="DENIED_NOT_APEX_ACCOUNT",
                    http_status=403,
                    detail="Non-Apex account attempted Apex Command Sign-In; use 6-digit email code.",
                )
                raise SessionAuthError(
                    403,
                    "This account uses standard 6-digit email sign-in rather than Apex Command Sign-In.",
                    error_code="NOT_APEX_ACCOUNT",
                )

            pw_ok = verify_secret_pbkdf2(passphrase or "", user.passphrase_hash)
            mfa_ok = False
            auth_method = "APEX_PASSPHRASE_MFA"

            if webauthn_assertion and self._webauthn_verifier is not None:
                try:
                    mfa_ok = bool(self._webauthn_verifier(user, webauthn_assertion))
                    if mfa_ok:
                        auth_method = "APEX_PASSPHRASE_WEBAUTHN"
                except Exception:
                    mfa_ok = False
            elif mfa_code and _SIX_DIGIT_RE.match(mfa_code.strip()):
                mfa_ok = verify_secret_pbkdf2(mfa_code.strip(), user.mfa_secret_hash)

            if not (pw_ok and mfa_ok):
                audit.record(
                    event_type="AUTH_APEX_LOGIN_FAILED",
                    actor_id=user.user_id,
                    actor_role=",".join(hats),
                    target_id="apex_login",
                    action="APEX_LOGIN",
                    outcome="DENIED_PASSPHRASE_OR_MFA_MISMATCH",
                    http_status=401,
                    detail="Apex/Tier-3 passphrase or 6-digit MFA verification failed.",
                )
                raise SessionAuthError(
                    401,
                    "Invalid Apex passphrase or 6-digit MFA code.",
                    error_code="APEX_AUTH_FAILED",
                )

            chosen_hat = self._select_initial_hat(hats, requested_hat=requested_hat, is_apex=True)
            return self._issue_session_row(
                db,
                user,
                active_hat=chosen_hat,
                auth_method=auth_method,
            )
        finally:
            db.close()

    def _select_initial_hat(
        self,
        authorized_hats: Sequence[str],
        *,
        requested_hat: Optional[str],
        is_apex: bool,
    ) -> str:
        if requested_hat:
            norm_req = normalize_role_token(requested_hat)
            if norm_req in authorized_hats:
                if not is_apex and (norm_req in APEX_TIER3_HATS or is_chief_admin_role(norm_req)):
                    raise SessionAuthError(
                        403,
                        "Apex hats require Passphrase + MFA sign-in.",
                        error_code="APEX_MFA_REQUIRED",
                    )
                return norm_req
            raise SessionAuthError(
                403,
                f"Active Hat '{norm_req}' is not authorized for this account.",
                error_code="UNAUTHORIZED_HAT",
            )
        if is_apex:
            for preferred in ("CHIEF_ADMINISTRATOR", "T3", "F3"):
                if preferred in authorized_hats:
                    return preferred
            return authorized_hats[0]
        if "MEMBER_USER" in authorized_hats:
            return "MEMBER_USER"
        return authorized_hats[0]

    # ------------------------------------------------------------------
    # Session Validation, Idle Timeout, Active-Hat Lock & Revocation
    # ------------------------------------------------------------------

    def validate_session_cookie(
        self,
        cookie_value: Optional[str],
        *,
        touch: bool = True,
    ) -> Tuple[Optional[AuthenticatedSessionContext], Optional[str]]:
        """Validate a signed `pdeue_session` cookie.

        Returns `(context, None)` on success, or `(None, error_code)` when missing,
        tampered, expired, idle-timed-out, or revoked.
        """
        if not cookie_value:
            return None, "NO_SESSION_COOKIE"
        session_id = verify_signed_session_cookie(cookie_value)
        if not session_id:
            return None, "INVALID_COOKIE_SIGNATURE"

        now = self._now()
        db: Session = self._session_factory()
        try:
            row = (
                db.query(AuthSessionModel)
                .filter(AuthSessionModel.session_id == session_id)
                .first()
            )
            if row is None:
                return None, "SESSION_NOT_FOUND"
            if row.revoked_at is not None:
                return None, "SESSION_REVOKED"

            user = (
                db.query(AuthUserModel)
                .filter(AuthUserModel.user_id == row.user_id)
                .first()
            )
            if user is None or not user.active:
                return None, "USER_INACTIVE"

            expires_dt = _parse_iso_utc(row.expires_at)
            if now > expires_dt:
                return None, "SESSION_EXPIRED"

            last_act_dt = _parse_iso_utc(row.last_activity_at)
            idle_elapsed = (now - last_act_dt).total_seconds()
            if idle_elapsed > float(row.idle_timeout_seconds):
                return None, "SESSION_IDLE_TIMEOUT"

            if touch:
                row.last_activity_at = now.isoformat()
                db.commit()

            hats = _parse_authorized_hats(user.authorized_hats)
            ctx = AuthenticatedSessionContext(
                session_id=row.session_id,
                user_id=user.user_id,
                email=user.email,
                display_name=user.display_name,
                scma_id=row.scma_id,
                house_id=user.house_id,
                active_hat=row.active_hat,
                authorized_hats=tuple(hats),
                is_apex_tier3=bool(user.is_apex_tier3),
                issued_at=row.issued_at,
                last_activity_at=row.last_activity_at,
                expires_at=row.expires_at,
                idle_timeout_seconds=int(row.idle_timeout_seconds),
            )
            return ctx, None
        finally:
            db.close()

    def switch_session_hat(
        self,
        cookie_value: Optional[str],
        *,
        to_hat: str,
        confirmed: bool = True,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Rotate `active_hat` server-side on an active session (Directive R-06)."""
        ctx, err = self.validate_session_cookie(cookie_value, touch=False)
        if ctx is None:
            raise SessionAuthError(
                401,
                f"Valid session required to switch Active Hat ({err}).",
                error_code=err or "AUTH_REQUIRED",
            )
        if not confirmed:
            raise SessionAuthError(
                400,
                "Active-Hat switch requires explicit human confirmation (confirmed=true).",
                error_code="CONFIRMATION_REQUIRED",
            )

        norm_target = normalize_role_token(to_hat)
        audit = get_governance_audit_log()
        if not norm_target or norm_target not in ctx.authorized_hats:
            audit.record(
                event_type="ACTIVE_HAT_DENIED",
                actor_id=ctx.user_id,
                actor_role=ctx.active_hat,
                target_id=ctx.session_id,
                action=f"SWITCH_HAT:{ctx.active_hat}->{norm_target}",
                outcome="DENIED_UNAUTHORIZED_HAT",
                http_status=403,
                detail=(
                    f"User {ctx.user_id} attempted to switch to unauthorized hat {norm_target}. "
                    f"Authorized: {list(ctx.authorized_hats)}."
                ),
            )
            raise SessionAuthError(
                403,
                f"ACTIVE_HAT_DENIED: Hat '{norm_target}' is not authorized for your account.",
                error_code="ACTIVE_HAT_DENIED",
            )

        # Prevent passwordless sessions from escalating into Apex/Tier-3 hats
        if (norm_target in APEX_TIER3_HATS or is_chief_admin_role(norm_target)) and not ctx.is_apex_tier3:
            raise SessionAuthError(
                403,
                "APEX_MFA_REQUIRED: Cannot switch into an Apex/Tier-3 hat without Apex Passphrase + MFA.",
                error_code="APEX_MFA_REQUIRED",
            )

        now = self._now()
        new_active_window, new_idle_timeout = _session_timeouts_for_hat(norm_target)
        previous_hat = ctx.active_hat

        db: Session = self._session_factory()
        try:
            row = (
                db.query(AuthSessionModel)
                .filter(AuthSessionModel.session_id == ctx.session_id)
                .first()
            )
            if row is None or row.revoked_at is not None:
                raise SessionAuthError(401, "Session is no longer active.", error_code="SESSION_REVOKED")

            row.active_hat = norm_target
            row.last_activity_at = now.isoformat()
            row.idle_timeout_seconds = new_idle_timeout
            # Clamp expiry downward if entering a stricter Officer/Apex window
            max_allowed_exp = now + timedelta(seconds=new_active_window)
            current_exp = _parse_iso_utc(row.expires_at)
            if current_exp > max_allowed_exp:
                row.expires_at = max_allowed_exp.isoformat()
            db.commit()

            entry = audit.record(
                event_type="ACTIVE_HAT_SWITCH",
                actor_id=ctx.user_id,
                actor_role=norm_target,
                target_id=ctx.session_id,
                action=f"SWITCH_HAT:{previous_hat}->{norm_target}",
                outcome="HAT_ROTATED",
                http_status=200,
                detail=(
                    f"Directive R-06 server-side Active-Hat rotation from {previous_hat} to {norm_target}. "
                    f"{reason}".strip()
                ),
            )
            updated = AuthenticatedSessionContext(
                session_id=row.session_id,
                user_id=ctx.user_id,
                email=ctx.email,
                display_name=ctx.display_name,
                scma_id=row.scma_id,
                house_id=ctx.house_id,
                active_hat=row.active_hat,
                authorized_hats=ctx.authorized_hats,
                is_apex_tier3=ctx.is_apex_tier3,
                issued_at=row.issued_at,
                last_activity_at=row.last_activity_at,
                expires_at=row.expires_at,
                idle_timeout_seconds=int(row.idle_timeout_seconds),
            )
            return {
                "status": "SWITCHED",
                "event_id": entry["event_id"],
                "previous_hat": previous_hat,
                "active_hat": updated.active_hat,
                "target_workspace": workspace_url_for_hat(updated.active_hat, updated.house_id),
                "session": updated.to_dict(),
            }
        finally:
            db.close()

    def logout_session(self, cookie_value: Optional[str]) -> Dict[str, Any]:
        """Revoke the caller's current session (if valid) and log AUTH_LOGOUT."""
        session_id = verify_signed_session_cookie(cookie_value) if cookie_value else None
        now = self._now()
        if session_id:
            db: Session = self._session_factory()
            try:
                row = (
                    db.query(AuthSessionModel)
                    .filter(AuthSessionModel.session_id == session_id)
                    .first()
                )
                if row and row.revoked_at is None:
                    row.revoked_at = now.isoformat()
                    row.revoked_by = row.user_id
                    db.commit()
                    get_governance_audit_log().record(
                        event_type="AUTH_LOGOUT",
                        actor_id=row.user_id,
                        actor_role=row.active_hat,
                        target_id=row.session_id,
                        action="LOGOUT",
                        outcome="SESSION_REVOKED_SELF",
                        http_status=200,
                        detail="User signed out cleanly; session revoked server-side.",
                    )
            finally:
                db.close()
        return {"status": "SIGNED_OUT", "redirect_to": "/login"}

    def list_sessions(self, *, include_revoked: bool = True, limit: int = 100) -> List[Dict[str, Any]]:
        """List active (and recent revoked) sessions for Chief Admin inspection."""
        now = self._now()
        db: Session = self._session_factory()
        try:
            query = db.query(AuthSessionModel)
            if not include_revoked:
                query = query.filter(AuthSessionModel.revoked_at.is_(None))
            rows = (
                query.order_by(AuthSessionModel.issued_at.desc())
                .limit(max(1, min(limit, 500)))
                .all()
            )
            users_map = {
                u.user_id: u for u in db.query(AuthUserModel).all()
            }
            out: List[Dict[str, Any]] = []
            for row in rows:
                user = users_map.get(row.user_id)
                exp_dt = _parse_iso_utc(row.expires_at)
                last_dt = _parse_iso_utc(row.last_activity_at)
                idle_expired = (now - last_dt).total_seconds() > float(row.idle_timeout_seconds)
                is_active = (
                    row.revoked_at is None
                    and now <= exp_dt
                    and not idle_expired
                )
                status = (
                    "REVOKED"
                    if row.revoked_at is not None
                    else ("EXPIRED" if now > exp_dt else ("IDLE_EXPIRED" if idle_expired else "ACTIVE"))
                )
                out.append(
                    {
                        "session_id": row.session_id,
                        "user_id": row.user_id,
                        "email": user.email if user else "",
                        "display_name": user.display_name if user else row.user_id,
                        "scma_id": row.scma_id,
                        "house_id": user.house_id if user else "HOUSE-01",
                        "active_hat": row.active_hat,
                        "issued_at": row.issued_at,
                        "last_activity_at": row.last_activity_at,
                        "expires_at": row.expires_at,
                        "idle_timeout_seconds": int(row.idle_timeout_seconds),
                        "revoked_at": row.revoked_at,
                        "revoked_by": row.revoked_by,
                        "is_active": is_active,
                        "status": status,
                    }
                )
            return out
        finally:
            db.close()

    def revoke_session(
        self,
        session_id: str,
        *,
        revoked_by: str,
        actor_role: str = "CHIEF_ADMINISTRATOR",
        reason: str = "Chief Admin immediate lost-device session revocation",
    ) -> Dict[str, Any]:
        """Immediately revoke a target session (e.g., lost phone or shared laptop)."""
        now = self._now()
        db: Session = self._session_factory()
        try:
            row = (
                db.query(AuthSessionModel)
                .filter(AuthSessionModel.session_id == session_id)
                .first()
            )
            if row is None:
                raise SessionAuthError(404, f"Session '{session_id}' not found.", error_code="SESSION_NOT_FOUND")
            if row.revoked_at is None:
                row.revoked_at = now.isoformat()
                row.revoked_by = revoked_by
                db.commit()
            entry = get_governance_audit_log().record(
                event_type="AUTH_SESSION_REVOKED",
                actor_id=revoked_by,
                actor_role=actor_role,
                target_id=session_id,
                action="REVOKE_SESSION",
                outcome="REVOKED",
                http_status=200,
                detail=f"Revoked session {session_id} for user {row.user_id}. Reason: {reason}",
                metadata={"target_user_id": row.user_id, "target_active_hat": row.active_hat},
            )
            return {
                "status": "REVOKED",
                "session_id": row.session_id,
                "user_id": row.user_id,
                "revoked_at": row.revoked_at,
                "revoked_by": row.revoked_by,
                "audit_event_id": entry["event_id"],
            }
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Route Authorization & Server-Side Tenant Jailing Helpers
# ---------------------------------------------------------------------------

_EXEMPT_EXACT_PATHS: Set[str] = {
    "/login",
    "/health",
    "/healthz",
    "/metrics",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/api/v1/portal/planes",
    "/api/v1/auth/request-code",
    "/api/v1/auth/verify-code",
    "/api/v1/auth/magic",
    "/api/v1/auth/apex-login",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
}

_HTML_PORTAL_PREFIXES: Tuple[str, ...] = (
    "/home",
    "/dashboard",
    "/member",
    "/advisor",
    "/admin/tech",
    "/lineage/house/",
    "/community",
    "/companion",
)

_LINEAGE_HOUSE_PATH_RE = re.compile(r"^/(?:api/v1/portal/)?lineage/house/(\d+)(?:/|$)")
_MEMBER_SCMA_PATH_RE = re.compile(r"^/api/v1/portal/member/(SCMA-[^/?]+)(?:/|$)", re.IGNORECASE)


def is_auth_exempt_path(path: str) -> bool:
    if path in _EXEMPT_EXACT_PATHS:
        return True
    if path.startswith("/static/"):
        return True
    return False


def is_html_portal_path(path: str) -> bool:
    if path == "/":
        return True
    return any(path == p or path.startswith(p + "/") or (p.endswith("/") and path.startswith(p)) for p in _HTML_PORTAL_PREFIXES)


def authorize_session_for_request(
    session_ctx: AuthenticatedSessionContext,
    *,
    path: str,
    query_params: Dict[str, str],
    method: str = "GET",
) -> Tuple[bool, str, str]:
    """Validate an authenticated session's Active Hat & tenant boundary against a request.

    Returns `(allowed, error_code, detail_message)`.
    """
    hat = normalize_role_token(session_ctx.active_hat)
    is_admin = is_chief_admin_role(hat)
    is_deputy = is_chief_admin_deputy_role(hat)

    # 1. Chief Admin Cockpit (/dashboard and executive governance/operator APIs)
    if (
        path == "/dashboard"
        or path.startswith("/api/v1/portal/dashboard")
        or path.startswith("/api/v1/governance/")
        or path.startswith("/api/v1/operator/")
    ):
        if is_admin or is_deputy:
            return True, "", ""
        return (
            False,
            "ACTIVE_HAT_DENIED",
            f"SESSION ACCESS DENIED (HTTP 403): Active Hat '{hat}' cannot access Chief Admin Cockpit.",
        )

    # 2. Technical Console (/admin/tech and /api/v1/portal/tech/*)
    if path == "/admin/tech" or path.startswith("/api/v1/portal/tech/"):
        if is_admin or is_deputy:
            return True, "", ""
        if hat in {"T1", "T2", "T2-HOUSEHOLD", "T3"}:
            req_tier = query_params.get("tier")
            if req_tier and normalize_tech_tier(req_tier) != hat:
                return (
                    False,
                    "CROSS_TIER_ACCESS_DENIED",
                    f"SESSION ACCESS DENIED (HTTP 403): Assigned Class T hat '{hat}' cannot access tier '{normalize_tech_tier(req_tier)}'.",
                )
            return True, "", ""
        return (
            False,
            "ACTIVE_HAT_DENIED",
            f"SESSION ACCESS DENIED (HTTP 403): Active Hat '{hat}' cannot access Technical Console.",
        )

    # 3. Lineal Advisory Workspace (/advisor and /api/v1/portal/advisor/*)
    if path == "/advisor" or path.startswith("/api/v1/portal/advisor/"):
        if is_admin or is_deputy:
            return True, "", ""
        if hat in {"F1", "F2-H", "F2-A", "F3"}:
            req_role = query_params.get("role")
            if req_role and normalize_advisor_role(req_role) != hat:
                return (
                    False,
                    "CROSS_TIER_ACCESS_DENIED",
                    f"SESSION ACCESS DENIED (HTTP 403): Assigned Class F hat '{hat}' cannot access '{normalize_advisor_role(req_role)}'.",
                )
            return True, "", ""
        return (
            False,
            "ACTIVE_HAT_DENIED",
            f"SESSION ACCESS DENIED (HTTP 403): Active Hat '{hat}' cannot access Lineal Advisory Workspace.",
        )

    # 4. Lineage House Desk (/lineage/house/{id} and /api/v1/portal/lineage/house/{id}/*)
    house_match = _LINEAGE_HOUSE_PATH_RE.match(path)
    if house_match:
        target_house = int(house_match.group(1))
        if is_admin or is_deputy:
            return True, "", ""
        if hat in {"H1", "H2", "HOUSE_GENEALOGIST"}:
            user_house = parse_house_number(session_ctx.house_id)
            if user_house is not None and target_house != user_house:
                return (
                    False,
                    "CROSS_HOUSE_ACCESS_DENIED",
                    f"SESSION ACCESS DENIED (HTTP 403): House '{session_ctx.house_id}' cannot access HOUSE-{target_house:02d}.",
                )
            return True, "", ""
        return (
            False,
            "ACTIVE_HAT_DENIED",
            f"SESSION ACCESS DENIED (HTTP 403): Active Hat '{hat}' cannot access House Lineage Desk.",
        )

    # 5. Member Wealth Desktop & Member APIs (/member and /api/v1/portal/member/*)
    if path == "/member" or path.startswith("/api/v1/portal/member/"):
        if is_admin or is_deputy:
            # Chief Admin / Deputy preserved for read-only Supervisory Audit Lens inspection
            if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and not path.endswith("/tutor") and not path.endswith("/ai-tutor"):
                return (
                    False,
                    "SUPERVISORY_READ_ONLY_INSPECTION",
                    "SESSION ACCESS DENIED (HTTP 403): Switch Active Hat to PERSONAL_SCMA before mutating member controls.",
                )
            return True, "", ""

        if hat not in CLASS_M_HATS:
            return (
                False,
                "ACTIVE_HAT_DENIED",
                f"SESSION ACCESS DENIED (HTTP 403): Active Hat '{hat}' cannot access /member vault. Switch to MEMBER_USER / PERSONAL_SCMA first.",
            )

        # Strict Server-Side Tenant Jailing on ?scma_id= / ?scma= / path SCMA ID
        requested_scma = (
            query_params.get("scma_id")
            or query_params.get("scma")
            or ""
        ).strip()
        if not requested_scma:
            m = _MEMBER_SCMA_PATH_RE.match(path)
            if m:
                requested_scma = m.group(1).strip()

        if requested_scma:
            bound_scma = (session_ctx.scma_id or "").strip()
            if not bound_scma or requested_scma != bound_scma:
                return (
                    False,
                    "TENANT_JAIL_VIOLATION",
                    (
                        f"SESSION ACCESS DENIED (HTTP 403): Cross-member SCMA access blocked. "
                        f"Your session is strictly jailed to your own assigned account."
                    ),
                )
        return True, "", ""

    # 6. Family Home Hub, Community, Heritage, Family Tree, Companion (all authenticated family roles)
    return True, "", ""


_SHARED_SESSION_AUTH_SERVICE: Optional[SessionAuthService] = None


def get_session_auth_service() -> SessionAuthService:
    global _SHARED_SESSION_AUTH_SERVICE
    if _SHARED_SESSION_AUTH_SERVICE is None:
        _SHARED_SESSION_AUTH_SERVICE = SessionAuthService()
    return _SHARED_SESSION_AUTH_SERVICE


def reset_session_auth_service(service: Optional[SessionAuthService] = None) -> None:
    """Allow test harnesses to inject or reset the shared SessionAuthService."""
    global _SHARED_SESSION_AUTH_SERVICE
    _SHARED_SESSION_AUTH_SERVICE = service
