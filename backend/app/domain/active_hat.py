"""In-process, fail-closed Active-Hat session authority for the Founder."""
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Dict, Literal
import uuid

from fastapi import HTTPException

from app.core.security import create_access_token, decode_access_token

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

    def select_hat(self, identity_token: str, hat: FounderHat, confirmed: bool) -> Dict[str, str]:
        identity = decode_access_token(identity_token)
        if not identity or identity.get("role") not in {"FOUNDER", "CHIEF_ADMIN"}:
            raise HTTPException(status_code=403, detail="FOUNDER_IDENTITY_REQUIRED")
        if not confirmed:
            raise HTTPException(status_code=400, detail="EXPLICIT_CONFIRMATION_REQUIRED")
        subject = identity.get("sub") or identity.get("user_id")
        if not subject:
            raise HTTPException(status_code=403, detail="IDENTITY_SUBJECT_REQUIRED")
        session_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        session = HatSession(session_id, str(subject), hat, "FOUNDER", now)
        with self._lock:
            old_id = self._current_by_subject.get(str(subject))
            if old_id:
                self._sessions.pop(old_id, None)
            self._sessions[session_id] = session
            self._current_by_subject[str(subject)] = session_id
        claims = {
            "sub": str(subject), "role": "FOUNDER", "active_hat": hat,
            "session_id": session_id, "issued_at_utc": now,
        }
        return {"access_token": create_access_token(claims), "token_type": "bearer", "active_hat": hat}

    def authorize(self, token: str, required_hat: FounderHat) -> HatSession:
        claims = decode_access_token(token)
        if not claims or claims.get("active_hat") != required_hat:
            raise HTTPException(status_code=403, detail="ACTIVE_HAT_MISMATCH")
        session_id = claims.get("session_id")
        subject = claims.get("sub")
        with self._lock:
            session = self._sessions.get(str(session_id))
            current = self._current_by_subject.get(str(subject))
        if not session or current != session_id or session.subject != subject or session.hat != required_hat:
            raise HTTPException(status_code=403, detail="SESSION_REVOKED_OR_STALE")
        return session

    def revoke_subject(self, subject: str) -> bool:
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

