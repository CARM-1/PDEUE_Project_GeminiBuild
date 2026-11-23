"""In-process, fail-closed Active-Hat session authority for the Founder."""
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Dict, Literal
import uuid

from fastapi import HTTPException

from app.core.security import create_access_token, decode_access_token
from app.domain.authority_tiers import (
    enforce_founder_immunity,
    get_governance_audit_log,
    is_founder_target,
)

FounderHat = Literal["CHIEF_ADMINISTRATOR", "PERSONAL_SCMA"]


@dataclass(frozen=True)
class HatSession:
    session_id: str
    subject: str
    hat: FounderHat
    role: str
    issued_at_utc: str


class ActiveHatSessionAuthority:
    """Tracks the one currently valid scoped session for each identity."""

    def __init__(self) -> None:
        self._sessions: Dict[str, HatSession] = {}
        self._current_by_subject: Dict[str, str] = {}
        self._lock = RLock()
        self._audit = get_governance_audit_log()

    def select_hat(self, identity_token: str, hat: FounderHat, confirmed: bool) -> Dict[str, str]:
        identity = decode_access_token(identity_token)
        if not identity or identity.get("role") not in {"FOUNDER", "CHIEF_ADMIN"}:
            self._audit.record(
                event_type="ACTIVE_HAT_DENIED",
                actor_id=str((identity or {}).get("sub") or "anonymous"),
                actor_role=str((identity or {}).get("role") or "UNAUTHENTICATED"),
                target_id=hat,
                action="SELECT_FOUNDER_HAT",
                outcome="DENIED_UNAUTHORIZED_IDENTITY",
                http_status=403,
                detail="Founder/Chief Admin identity required to select executive or personal Founder hat.",
            )
            raise HTTPException(status_code=403, detail="FOUNDER_IDENTITY_REQUIRED")
        if not confirmed:
            self._audit.record(
                event_type="ACTIVE_HAT_DENIED",
                actor_id=str(identity.get("sub") or identity.get("user_id") or "founder"),
                actor_role=str(identity.get("role")),
                target_id=hat,
                action="SELECT_FOUNDER_HAT",
                outcome="DENIED_UNCONFIRMED",
                http_status=400,
                detail="Explicit confirmation required for Active-Hat switch.",
            )
            raise HTTPException(status_code=400, detail="EXPLICIT_CONFIRMATION_REQUIRED")
        subject = identity.get("sub") or identity.get("user_id")
        if not subject:
            raise HTTPException(status_code=403, detail="IDENTITY_SUBJECT_REQUIRED")
        session_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        session = HatSession(session_id, str(subject), hat, "FOUNDER", now)
        previous_hat = None
        with self._lock:
            old_id = self._current_by_subject.get(str(subject))
            if old_id:
                old_session = self._sessions.pop(old_id, None)
                previous_hat = old_session.hat if old_session else None
            self._sessions[session_id] = session
            self._current_by_subject[str(subject)] = session_id
        claims = {
            "sub": str(subject), "role": "FOUNDER", "active_hat": hat,
            "session_id": session_id, "issued_at_utc": now,
        }
        audit_entry = self._audit.record(
            event_type="ACTIVE_HAT_SWITCH",
            actor_id=str(subject),
            actor_role="FOUNDER",
            target_id=hat,
            action="SELECT_FOUNDER_HAT",
            outcome="SWITCHED",
            http_status=200,
            detail=f"Founder Active-Hat context switched from {previous_hat or 'NONE'} to {hat}.",
            metadata={"from_hat": previous_hat, "to_hat": hat, "session_id": session_id},
        )
        return {
            "access_token": create_access_token(claims),
            "token_type": "bearer",
            "active_hat": hat,
            "audit_event_id": audit_entry["event_id"],
        }

    def authorize(self, token: str, required_hat: FounderHat) -> HatSession:
        claims = decode_access_token(token)
        if not claims or claims.get("active_hat") != required_hat:
            self._audit.record(
                event_type="ACTIVE_HAT_DENIED",
                actor_id=str((claims or {}).get("sub") or "anonymous"),
                actor_role=str((claims or {}).get("active_hat") or (claims or {}).get("role") or "UNKNOWN"),
                target_id=required_hat,
                action="AUTHORIZE_HAT_ROUTE",
                outcome="DENIED_HAT_MISMATCH",
                http_status=403,
                detail=f"Active-Hat mismatch: required {required_hat}.",
            )
            raise HTTPException(status_code=403, detail="ACTIVE_HAT_MISMATCH")
        session_id = claims.get("session_id")
        subject = claims.get("sub")
        with self._lock:
            session = self._sessions.get(str(session_id))
            current = self._current_by_subject.get(str(subject))
        if not session or current != session_id or session.subject != subject or session.hat != required_hat:
            self._audit.record(
                event_type="ACTIVE_HAT_DENIED",
                actor_id=str(subject or "unknown"),
                actor_role=str(claims.get("active_hat") or "UNKNOWN"),
                target_id=required_hat,
                action="AUTHORIZE_HAT_ROUTE",
                outcome="DENIED_REVOKED_OR_STALE",
                http_status=403,
                detail="Session revoked or superseded by newer Active-Hat switch.",
            )
            raise HTTPException(status_code=403, detail="SESSION_REVOKED_OR_STALE")
        return session

    def revoke_subject(self, subject: str, *, actor_role: str = "SUBORDINATE", actor_id: str = "unknown") -> bool:
        if is_founder_target(subject):
            enforce_founder_immunity(
                target_id=subject,
                action="REVOKE_IDENTITY",
                actor_role=actor_role,
                actor_id=actor_id,
            )
        with self._lock:
            session_id = self._current_by_subject.pop(subject, None)
            return self._sessions.pop(session_id, None) is not None if session_id else False

    def privileged_sessions(self):
        with self._lock:
            return [
                {"subject": s.subject, "role": s.role, "active_hat": s.hat,
                 "issued_at_utc": s.issued_at_utc}
                for s in self._sessions.values() if s.role in {"T2", "T3"}
            ]

