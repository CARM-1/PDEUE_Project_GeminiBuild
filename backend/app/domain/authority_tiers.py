"""Milestones C2-C5 — Authority Tiers, Directive R-06 Active-Hat, C3 Founder Immunity,
Class T (T1/T2/T2-Household/T3) + Directive R-12 Time-Bounded CA Override,
and Class F (F1/F2-H/F2-A/F3) + Directive R-04 Dual-Control Governance Engine.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Set
import time
import uuid

from fastapi import HTTPException

from app.core.security import create_access_token, decode_access_token


FOUNDER_SCMA_IDS: Set[str] = {
    "SCMA-FOUNDER_-C8575D7E",
    "FOUNDER_SCMA",
}

FOUNDER_IDENTITY_IDS: Set[str] = {
    "USR-founder_ch-C8575D7E",
    "founder-1",
    "FOUNDER",
    "CHIEF_ADMIN",
    "CHIEF_ADMINISTRATOR",
    "SCMA-FOUNDER_-C8575D7E",
    "FOUNDER_SCMA",
}

CHIEF_ADMIN_ROLES: Set[str] = {
    "FOUNDER",
    "CHIEF_ADMIN",
    "CHIEF_ADMINISTRATOR",
}

CLASS_T_TIERS: Set[str] = {
    "T1",
    "T2",
    "T2-HOUSEHOLD",
    "T3",
    "TECHNICAL_OPERATOR",
    "T1_MONITOR",
    "T2_ENGINEER",
    "T2_HOUSEHOLD",
    "T3_CTO",
    "T3_SYSTEM_ADMIN",
}

CLASS_F_ROLES: Set[str] = {
    "F1",
    "F2",
    "F2-H",
    "F2-A",
    "F3",
    "F1_PEER_GUIDE",
    "F2_FINANCIAL_ADVISOR",
    "F2-H_HOUSEHOLD_HEAD",
    "F2-A_LINEAGE_ADVISOR",
    "F3_CRO_RISK",
    "F3_FINANCIAL_ADVISOR",
    "FINANCIAL_ADVISOR",
}

CLASS_H_ROLES: Set[str] = {"H1", "H2", "CLASS_H_LEADER"}

CLASS_M_ROLES: Set[str] = {"MEMBER_USER", "PERSONAL_SCMA", "MEMBER", "CLASS_M"}

HAT_WORKSPACES: Dict[str, str] = {
    "CHIEF_ADMINISTRATOR": "/dashboard",
    "PERSONAL_SCMA": "/member",
    "MEMBER_USER": "/member",
    "T1": "/admin/tech?tier=T1",
    "T2": "/admin/tech?tier=T2",
    "T2-HOUSEHOLD": "/admin/tech?tier=T2-Household",
    "T3": "/admin/tech?tier=T3",
    "F1": "/advisor?role=F1",
    "F2-H": "/advisor?role=F2-H",
    "F2-A": "/advisor?role=F2-A",
    "F3": "/advisor?role=F3",
    "H1": "/lineage/house/1?role=H1",
    "H2": "/lineage/house/1?role=H2",
}

PRINCIPAL_HAT_ENTITLEMENTS: Dict[str, Set[str]] = {
    "USR-founder_ch-C8575D7E": {"CHIEF_ADMINISTRATOR", "PERSONAL_SCMA", "MEMBER_USER"},
    "SCMA-FOUNDER_-C8575D7E": {"CHIEF_ADMINISTRATOR", "PERSONAL_SCMA", "MEMBER_USER"},
    "founder-1": {"CHIEF_ADMINISTRATOR", "PERSONAL_SCMA", "MEMBER_USER"},
    "FOUNDER": {"CHIEF_ADMINISTRATOR", "PERSONAL_SCMA", "MEMBER_USER"},
    "CHIEF_ADMIN": {"CHIEF_ADMINISTRATOR", "PERSONAL_SCMA", "MEMBER_USER"},
    "CHIEF_ADMINISTRATOR": {"CHIEF_ADMINISTRATOR", "PERSONAL_SCMA", "MEMBER_USER"},
    "USR-eleanor_va-B2B31C9E": {"F2-H", "MEMBER_USER", "PERSONAL_SCMA"},
    "SCMA-ELEANOR_-B2B31C9E": {"F2-H", "MEMBER_USER", "PERSONAL_SCMA"},
    "USR-julian_va-A1F98B21": {"MEMBER_USER", "PERSONAL_SCMA"},
}

ROLE_DEFAULT_HATS: Dict[str, Set[str]] = {
    "FOUNDER": {"CHIEF_ADMINISTRATOR", "PERSONAL_SCMA", "MEMBER_USER"},
    "CHIEF_ADMIN": {"CHIEF_ADMINISTRATOR", "PERSONAL_SCMA", "MEMBER_USER"},
    "CHIEF_ADMINISTRATOR": {"CHIEF_ADMINISTRATOR", "PERSONAL_SCMA", "MEMBER_USER"},
    "T1": {"T1"},
    "T2": {"T2"},
    "T2-HOUSEHOLD": {"T2-HOUSEHOLD"},
    "T3": {"T3"},
    "F1": {"F1"},
    "F2-H": {"F2-H", "MEMBER_USER", "PERSONAL_SCMA"},
    "F2-A": {"F2-A"},
    "F3": {"F3"},
    "H1": {"H1"},
    "H2": {"H2", "MEMBER_USER", "PERSONAL_SCMA"},
    "MEMBER_USER": {"MEMBER_USER", "PERSONAL_SCMA"},
    "PERSONAL_SCMA": {"MEMBER_USER", "PERSONAL_SCMA"},
}


def normalize_role_token(raw: Optional[str]) -> str:
    """Normalize role / sub-tier aliases into canonical uppercase codes."""
    if not raw:
        return ""
    token = raw.strip().upper().replace("_", "-")
    aliases = {
        "CHIEF-ADMIN": "CHIEF_ADMINISTRATOR",
        "CHIEF-ADMINISTRATOR": "CHIEF_ADMINISTRATOR",
        "FOUNDER": "CHIEF_ADMINISTRATOR",
        "T1-MONITOR": "T1",
        "T2-ENGINEER": "T2",
        "T2-HOUSEHOLD": "T2-HOUSEHOLD",
        "T3-CTO": "T3",
        "T3-SYSTEM-ADMIN": "T3",
        "TECHNICAL-OPERATOR": "T3",
        "F1-PEER-GUIDE": "F1",
        "F2-H-HOUSEHOLD-HEAD": "F2-H",
        "F2-FINANCIAL-ADVISOR": "F2-H",
        "F2-A-LINEAGE-ADVISOR": "F2-A",
        "F3-CRO-RISK": "F3",
        "F3-FINANCIAL-ADVISOR": "F3",
        "MEMBER-USER": "MEMBER_USER",
        "PERSONAL-SCMA": "PERSONAL_SCMA",
        "CLASS-M": "MEMBER_USER",
        "HOUSE-ASSISTANT": "H1",
        "HOUSE-LEADER": "H2",
    }
    return aliases.get(token, token)


def normalize_tech_tier(raw: Optional[str]) -> str:
    """Normalize Class T sub-tier strings (T1, T2, T2-HOUSEHOLD, T3)."""
    if not raw:
        return "T1"
    token = normalize_role_token(raw)
    if token in {"T1", "T2", "T2-HOUSEHOLD", "T3"}:
        return token
    return "T1"


def normalize_advisor_role(raw: Optional[str]) -> str:
    """Normalize Class F sub-tier strings (F1, F2-H, F2-A, F3)."""
    token = normalize_role_token(raw)
    if token in {"F1", "F2-H", "F2-A", "F3"}:
        return token
    return token


def is_chief_admin_role(raw: Optional[str]) -> bool:
    return normalize_role_token(raw) == "CHIEF_ADMINISTRATOR"


def is_class_t_role(raw: Optional[str]) -> bool:
    if not raw:
        return False
    norm = normalize_role_token(raw)
    return norm in {"T1", "T2", "T2-HOUSEHOLD", "T3"} or raw.strip().upper() in CLASS_T_TIERS


def is_founder_target(target: Any) -> bool:
    """Return True if target identifier or account dict refers to Founder/Chief Admin."""
    if target is None:
        return False
    if isinstance(target, dict):
        if target.get("role_tag") == "Sovereign Settlor":
            return True
        for key in ("scma_id", "user_id", "member_id", "subject", "role"):
            val = target.get(key)
            if val and is_founder_target(str(val)):
                return True
        return False
    text = str(target).strip()
    upper = text.upper()
    if text in FOUNDER_IDENTITY_IDS or upper in {x.upper() for x in FOUNDER_IDENTITY_IDS}:
        return True
    if upper.startswith("SCMA-FOUNDER") or upper.startswith("USR-FOUNDER"):
        return True
    return False


class GovernanceAuditLog:
    """Thread-safe append-only governance and security audit ledger."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._events: List[Dict[str, Any]] = []

    def record(
        self,
        *,
        event_type: str,
        actor_id: str,
        actor_role: str,
        action: str,
        outcome: str,
        http_status: int,
        target_id: str = "",
        detail: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = {
            "event_id": f"AUD-{uuid.uuid4().hex[:10].upper()}",
            "event_type": event_type,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "actor_id": actor_id or "anonymous",
            "actor_role": actor_role or "UNSPECIFIED",
            "target_id": target_id,
            "action": action,
            "outcome": outcome,
            "http_status": int(http_status),
            "detail": detail,
            "metadata": dict(metadata or {}),
        }
        with self._lock:
            self._events.append(entry)
        return dict(entry)

    def list_events(
        self,
        *,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._events)
        if event_type:
            items = [e for e in items if e["event_type"] == event_type]
        return list(reversed(items[-max(1, limit):]))


class ActiveHatGateway:
    """Server-validated Directive R-06 Active-Hat context switcher for multi-role principals."""

    def __init__(self, audit_log: GovernanceAuditLog) -> None:
        self._audit = audit_log
        self._lock = RLock()
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._current_by_principal: Dict[str, str] = {}

    def entitled_hats(
        self,
        principal_id: str,
        principal_role: Optional[str] = None,
        claims: Optional[Dict[str, Any]] = None,
    ) -> Set[str]:
        hats: Set[str] = set()
        if principal_id in PRINCIPAL_HAT_ENTITLEMENTS:
            hats |= set(PRINCIPAL_HAT_ENTITLEMENTS[principal_id])
        norm_role = normalize_role_token(principal_role)
        if norm_role in ROLE_DEFAULT_HATS:
            hats |= set(ROLE_DEFAULT_HATS[norm_role])
        if claims:
            claim_role = normalize_role_token(claims.get("role"))
            if claim_role in ROLE_DEFAULT_HATS:
                hats |= set(ROLE_DEFAULT_HATS[claim_role])
            for raw_hat in claims.get("entitled_hats") or []:
                hats.add(normalize_role_token(str(raw_hat)))
        return hats

    def switch_hat(
        self,
        *,
        principal_id: str,
        principal_role: str,
        from_hat: Optional[str],
        to_hat: str,
        confirmed: bool,
        target_workspace: Optional[str] = None,
        reason: str = "",
        identity_claims: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        norm_from = normalize_role_token(from_hat) if from_hat else ""
        norm_to = normalize_role_token(to_hat)
        norm_role = normalize_role_token(principal_role)

        if not confirmed:
            self._audit.record(
                event_type="ACTIVE_HAT_DENIED",
                actor_id=principal_id,
                actor_role=norm_role or norm_from or "UNKNOWN",
                target_id=norm_to,
                action="SWITCH_ACTIVE_HAT",
                outcome="DENIED_UNCONFIRMED",
                http_status=400,
                detail="Explicit Switch Active Hat confirmation is required before crossing workspace boundaries.",
                metadata={"from_hat": norm_from, "to_hat": norm_to},
            )
            raise HTTPException(
                status_code=400,
                detail="EXPLICIT_CONFIRMATION_REQUIRED: Crossing workspace boundaries requires explicit Switch Active Hat confirmation.",
            )

        if norm_to not in HAT_WORKSPACES:
            self._audit.record(
                event_type="ACTIVE_HAT_DENIED",
                actor_id=principal_id,
                actor_role=norm_role or "UNKNOWN",
                target_id=norm_to,
                action="SWITCH_ACTIVE_HAT",
                outcome="DENIED_UNKNOWN_HAT",
                http_status=422,
                detail=f"Unsupported target hat: {to_hat}",
            )
            raise HTTPException(status_code=422, detail=f"Unsupported Active Hat: {to_hat}")

        allowed = self.entitled_hats(principal_id, norm_role, identity_claims)
        if norm_to not in allowed:
            self._audit.record(
                event_type="ACTIVE_HAT_DENIED",
                actor_id=principal_id,
                actor_role=norm_role or "UNKNOWN",
                target_id=norm_to,
                action="SWITCH_ACTIVE_HAT",
                outcome="DENIED_UNAUTHORIZED_HAT",
                http_status=403,
                detail=f"Principal {principal_id} ({norm_role}) is not authorized to assume Active Hat {norm_to}.",
                metadata={"from_hat": norm_from, "to_hat": norm_to, "entitled_hats": sorted(allowed)},
            )
            raise HTTPException(
                status_code=403,
                detail=f"UNAUTHORIZED_HAT_SWITCH: Principal {principal_id} cannot assume Active Hat {norm_to}.",
            )

        session_id = uuid.uuid4().hex
        now_utc = datetime.now(timezone.utc).isoformat()
        resolved_workspace = target_workspace or HAT_WORKSPACES[norm_to]
        previous_revoked = False

        with self._lock:
            old_sid = self._current_by_principal.get(principal_id)
            if old_sid:
                self._active_sessions.pop(old_sid, None)
                previous_revoked = True
            session_record = {
                "session_id": session_id,
                "principal_id": principal_id,
                "principal_role": norm_role or norm_to,
                "from_hat": norm_from or None,
                "active_hat": norm_to,
                "target_workspace": resolved_workspace,
                "issued_at_utc": now_utc,
                "reason": reason,
            }
            self._active_sessions[session_id] = session_record
            self._current_by_principal[principal_id] = session_id

        claims = {
            "sub": principal_id,
            "role": norm_role or norm_to,
            "active_hat": norm_to,
            "previous_hat": norm_from or None,
            "session_id": session_id,
            "target_workspace": resolved_workspace,
            "issued_at_utc": now_utc,
        }
        access_token = create_access_token(claims)

        audit_event = self._audit.record(
            event_type="ACTIVE_HAT_SWITCH",
            actor_id=principal_id,
            actor_role=norm_role or norm_to,
            target_id=norm_to,
            action="SWITCH_ACTIVE_HAT",
            outcome="SWITCHED",
            http_status=200,
            detail=f"Directive R-06 Active-Hat switch: {norm_from or 'INITIAL'} -> {norm_to} ({resolved_workspace})",
            metadata={
                "from_hat": norm_from or None,
                "to_hat": norm_to,
                "session_id": session_id,
                "target_workspace": resolved_workspace,
                "previous_session_revoked": previous_revoked,
                "reason": reason,
            },
        )
        return {
            "event_id": audit_event["event_id"],
            "access_token": access_token,
            "token_type": "bearer",
            "principal_id": principal_id,
            "from_hat": norm_from or None,
            "active_hat": norm_to,
            "target_workspace": resolved_workspace,
            "session_id": session_id,
            "previous_session_revoked": previous_revoked,
            "timestamp_utc": now_utc,
        }

    def verify_token(
        self,
        token: str,
        required_hats: Iterable[str],
        *,
        action: str,
        target_id: str = "",
    ) -> Dict[str, Any]:
        claims = decode_access_token(token)
        if not claims:
            self._audit.record(
                event_type="ACTIVE_HAT_DENIED",
                actor_id="unknown",
                actor_role="INVALID_TOKEN",
                target_id=target_id,
                action=action,
                outcome="DENIED_INVALID_TOKEN",
                http_status=403,
                detail="Invalid or expired Active-Hat token.",
            )
            raise HTTPException(status_code=403, detail="INVALID_OR_EXPIRED_ACTIVE_HAT_TOKEN")

        subject = str(claims.get("sub") or claims.get("user_id") or "unknown")
        active_hat = normalize_role_token(claims.get("active_hat") or claims.get("role"))
        allowed = {normalize_role_token(h) for h in required_hats}

        session_id = claims.get("session_id")
        if session_id:
            with self._lock:
                session = self._active_sessions.get(str(session_id))
                current = self._current_by_principal.get(subject)
            if not session or current != session_id:
                self._audit.record(
                    event_type="ACTIVE_HAT_DENIED",
                    actor_id=subject,
                    actor_role=active_hat,
                    target_id=target_id,
                    action=action,
                    outcome="DENIED_SESSION_REVOKED",
                    http_status=403,
                    detail="Active-Hat session has been revoked or superseded by a newer context switch.",
                )
                raise HTTPException(status_code=403, detail="SESSION_REVOKED_OR_STALE")

        if active_hat not in allowed:
            self._audit.record(
                event_type="ACTIVE_HAT_DENIED",
                actor_id=subject,
                actor_role=active_hat,
                target_id=target_id,
                action=action,
                outcome="DENIED_CROSS_HAT",
                http_status=403,
                detail=f"Directive R-06 violation: Active Hat {active_hat} cannot invoke {action}; required one of {sorted(allowed)}.",
            )
            raise HTTPException(
                status_code=403,
                detail=f"ACTIVE_HAT_MISMATCH: Active Hat {active_hat} is not permitted for {action}. Switch Active Hat first.",
            )
        return claims

    def current_session(self, principal_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            sid = self._current_by_principal.get(principal_id)
            return dict(self._active_sessions[sid]) if sid and sid in self._active_sessions else None


class CAOverrideManager:
    """Time-bounded, audited Chief Admin Override manager for Directive R-12."""

    LEGACY_OVERRIDE_SECRET = "CA-OVERRIDE-SECRET-DEV"
    LEGACY_UNREDACT_TOKEN = "AUTH-CA-OVERRIDE-TEMP"

    def __init__(self, audit_log: GovernanceAuditLog) -> None:
        self._audit = audit_log
        self._lock = RLock()
        self._grants: Dict[str, Dict[str, Any]] = {}

    def issue_grant(
        self,
        *,
        tier: str,
        secret_token: str,
        actor_id: str = "T3_CTO",
        reason: str = "Audited incident diagnostics",
        ttl_seconds: int = 300,
    ) -> Dict[str, Any]:
        norm_tier = normalize_tech_tier(tier)
        if norm_tier != "T3":
            self._audit.record(
                event_type="CA_OVERRIDE_DENIED",
                actor_id=actor_id,
                actor_role=norm_tier,
                target_id="DIRECTIVE_R12_UNREDACT",
                action="REQUEST_CA_OVERRIDE",
                outcome="DENIED_INSUFFICIENT_TIER",
                http_status=403,
                detail=f"Class T sub-tier {norm_tier} is prohibited from requesting CA R-12 override.",
            )
            raise HTTPException(status_code=403, detail="CA override requires T3 CTO authority")

        if secret_token != self.LEGACY_OVERRIDE_SECRET:
            self._audit.record(
                event_type="CA_OVERRIDE_DENIED",
                actor_id=actor_id,
                actor_role="T3",
                target_id="DIRECTIVE_R12_UNREDACT",
                action="REQUEST_CA_OVERRIDE",
                outcome="DENIED_INVALID_SECRET",
                http_status=401,
                detail="Invalid CA override token; Directive R-12 masking remains active.",
            )
            raise HTTPException(
                status_code=401,
                detail="Invalid CA override token; Directive R-12 masking remains active",
            )

        bounded_ttl = max(1, min(int(ttl_seconds), 900))
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=bounded_ttl)
        grant_id = f"CA-OVRD-{uuid.uuid4().hex[:8].upper()}"
        grant_token = f"CA-GRANT-{uuid.uuid4().hex[:16].upper()}"

        record = {
            "grant_id": grant_id,
            "grant_token": grant_token,
            "tier": "T3",
            "actor_id": actor_id,
            "reason": reason or "Audited incident diagnostics",
            "ttl_seconds": bounded_ttl,
            "issued_at_utc": now.isoformat(),
            "expires_at_utc": expires_at.isoformat(),
            "expires_at_epoch": time.time() + bounded_ttl,
            "revoked": False,
        }
        with self._lock:
            self._grants[grant_token] = record

        audit_event = self._audit.record(
            event_type="CA_OVERRIDE_GRANTED",
            actor_id=actor_id,
            actor_role="T3",
            target_id=grant_id,
            action="ACTIVATE_CA_OVERRIDE",
            outcome="GRANTED",
            http_status=200,
            detail=f"Time-bounded ({bounded_ttl}s) Chief Admin R-12 override granted to T3 CTO.",
            metadata={"grant_id": grant_id, "ttl_seconds": bounded_ttl, "expires_at_utc": record["expires_at_utc"]},
        )
        return {**record, "audit_event_id": audit_event["event_id"]}

    def validate_token(self, tier: str, token: Optional[str]) -> Optional[Dict[str, Any]]:
        norm_tier = normalize_tech_tier(tier)
        if norm_tier != "T3" or not token:
            return None
        if token == self.LEGACY_UNREDACT_TOKEN:
            return {
                "grant_id": "CA-OVRD-LEGACY-TEMP",
                "grant_token": token,
                "tier": "T3",
                "expires_at_utc": (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat(),
                "revoked": False,
            }
        with self._lock:
            grant = self._grants.get(token)
        if not grant:
            return None
        if grant["revoked"] or time.time() > float(grant["expires_at_epoch"]):
            self._audit.record(
                event_type="CA_OVERRIDE_EXPIRED",
                actor_id=grant["actor_id"],
                actor_role="T3",
                target_id=grant["grant_id"],
                action="VALIDATE_CA_OVERRIDE",
                outcome="EXPIRED_OR_REVOKED",
                http_status=401,
                detail="Time-bounded CA override token expired or revoked; Directive R-12 masking re-engaged.",
            )
            return None
        return dict(grant)

    def revoke_grant(self, token_or_id: Optional[str], actor_id: str = "T3_CTO") -> Dict[str, Any]:
        revoked_ids: List[str] = []
        with self._lock:
            for key, grant in self._grants.items():
                if not token_or_id or key == token_or_id or grant["grant_id"] == token_or_id:
                    grant["revoked"] = True
                    revoked_ids.append(grant["grant_id"])
        audit_event = self._audit.record(
            event_type="CA_OVERRIDE_REVOKED",
            actor_id=actor_id,
            actor_role="T3",
            target_id=",".join(revoked_ids) if revoked_ids else "ALL_ACTIVE",
            action="REVOKE_CA_OVERRIDE",
            outcome="REVOKED",
            http_status=200,
            detail="Chief Admin R-12 override revoked; Directive R-12 masking restored.",
        )
        return {"status": "REVOKED", "redaction_active": True, "revoked_grants": revoked_ids, "audit_event_id": audit_event["event_id"]}

    def force_expire_for_test(self, grant_token: str) -> None:
        """Expire a grant immediately (used by deterministic unit tests)."""
        with self._lock:
            if grant_token in self._grants:
                self._grants[grant_token]["expires_at_epoch"] = time.time() - 10.0


class DirectiveR04Controller:
    """Directive R-04 Emergency Halt (F3/CA) & Chief-Admin-Only Resumption + Dual-Sig Override."""

    def __init__(self, audit_log: GovernanceAuditLog) -> None:
        self._audit = audit_log
        self._lock = RLock()
        self.status: str = "NORMAL"
        self.failsafe: str = "ARMED"
        self.halted_by: Optional[str] = None
        self.halted_at_utc: Optional[str] = None
        self.halt_reason: Optional[str] = None
        self.resumed_by: Optional[str] = None
        self.resumed_at_utc: Optional[str] = None
        self._overrides: Dict[str, Dict[str, Any]] = {}
        self._seq: int = 0

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": self.status,
                "failsafe": self.failsafe,
                "halted_by": self.halted_by,
                "halted_at_utc": self.halted_at_utc,
                "halt_reason": self.halt_reason,
                "resumed_by": self.resumed_by,
                "resumed_at_utc": self.resumed_at_utc,
                "resumption_authority": "CHIEF_ADMINISTRATOR_ONLY",
            }

    def trigger_halt(self, *, actor_role: str, actor_id: str, reason: str) -> Dict[str, Any]:
        norm_role = normalize_role_token(actor_role)
        if norm_role not in {"F3", "CHIEF_ADMINISTRATOR"}:
            self._audit.record(
                event_type="ROLE_BOUNDARY_DENIED",
                actor_id=actor_id,
                actor_role=norm_role or "UNKNOWN",
                target_id="DIRECTIVE_R04",
                action="EMERGENCY_HALT",
                outcome="DENIED",
                http_status=403,
                detail=f"Role {norm_role} lacks Directive R-04 emergency halt authority (F3 CRO or Chief Admin required).",
            )
            raise HTTPException(
                status_code=403,
                detail="F3 CRO or Chief Administrator authority is required to engage Directive R-04 Emergency Halt",
            )
        if not reason or not reason.strip():
            raise HTTPException(status_code=422, detail="Emergency halt reason is required")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.status = "HALTED"
            self.failsafe = "ENGAGED"
            self.halted_by = norm_role
            self.halted_at_utc = now
            self.halt_reason = reason.strip()
        audit_event = self._audit.record(
            event_type="DIRECTIVE_R04_HALT",
            actor_id=actor_id,
            actor_role=norm_role,
            target_id="DIRECTIVE_R04",
            action="EMERGENCY_HALT",
            outcome="HALTED",
            http_status=200,
            detail=f"Directive R-04 Emergency Financial Halt engaged by {norm_role}: {reason.strip()}",
        )
        return {**self.snapshot(), "audit_event_id": audit_event["event_id"]}

    def resume(self, *, actor_role: str, actor_id: str, justification: str) -> Dict[str, Any]:
        norm_role = normalize_role_token(actor_role)
        if norm_role != "CHIEF_ADMINISTRATOR":
            self._audit.record(
                event_type="DIRECTIVE_R04_RESUME_DENIED",
                actor_id=actor_id,
                actor_role=norm_role or "UNKNOWN",
                target_id="DIRECTIVE_R04",
                action="EMERGENCY_RESUME",
                outcome="DENIED_NON_CA_RESUMPTION",
                http_status=403,
                detail=f"Blocked non-Chief-Admin ({norm_role}) attempt to lift Directive R-04 halt.",
            )
            raise HTTPException(
                status_code=403,
                detail="CHIEF_ADMIN_RESUMPTION_ONLY: Directive R-04 resumption is strictly reserved to the Chief Administrator.",
            )
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.status = "NORMAL"
            self.failsafe = "ARMED"
            self.resumed_by = "CHIEF_ADMINISTRATOR"
            self.resumed_at_utc = now
        audit_event = self._audit.record(
            event_type="DIRECTIVE_R04_RESUME",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id="DIRECTIVE_R04",
            action="EMERGENCY_RESUME",
            outcome="RESUMED",
            http_status=200,
            detail=f"Directive R-04 halt lifted by Chief Administrator: {justification.strip() or 'Verified safe'}",
        )
        return {**self.snapshot(), "audit_event_id": audit_event["event_id"]}

    def submit_dual_signature_override(
        self,
        *,
        actor_role: str,
        actor_id: str,
        target_scope: str,
        action: str,
        justification: str,
    ) -> Dict[str, Any]:
        norm_role = normalize_role_token(actor_role)
        if norm_role not in {"F3", "CHIEF_ADMINISTRATOR"}:
            self._audit.record(
                event_type="DUAL_SIG_DENIED",
                actor_id=actor_id,
                actor_role=norm_role or "UNKNOWN",
                target_id=target_scope,
                action="SUBMIT_DUAL_SIG_OVERRIDE",
                outcome="DENIED",
                http_status=403,
                detail=f"Role {norm_role} cannot submit platform dual-signature risk overrides (F3 CRO required).",
            )
            raise HTTPException(
                status_code=403,
                detail="F3 CRO authority is required to submit dual-signature risk overrides",
            )
        if is_founder_target(target_scope):
            self._audit.record(
                event_type="FOUNDER_IMMUNITY_BLOCK",
                actor_id=actor_id,
                actor_role=norm_role,
                target_id=target_scope,
                action="SUBMIT_DUAL_SIG_OVERRIDE",
                outcome="DENIED_FOUNDER_IMMUNE",
                http_status=403,
                detail="Founder/Chief Administrator identity and SCMA are immune from subordinate override petitions.",
            )
            raise HTTPException(
                status_code=403,
                detail="FOUNDER_APEX_IMMUNITY_VIOLATION: Founder/Chief Administrator identity and SCMA cannot be targeted.",
            )
        if not target_scope.strip() or not justification.strip():
            raise HTTPException(status_code=422, detail="target_scope and justification are required")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._seq += 1
            override_id = f"DSIG-R04-{self._seq:04d}"
            record = {
                "override_id": override_id,
                "submitted_by": norm_role,
                "actor_id": actor_id,
                "target_scope": target_scope.strip(),
                "action": action.strip().upper() or "RISK_CAP_OVERRIDE",
                "justification": justification.strip(),
                "status": "PENDING_CHIEF_ADMIN_COUNTERSIGN",
                "requires_chief_admin_countersign": True,
                "submitted_at_utc": now,
                "countersigned_by": None,
                "countersigned_at_utc": None,
            }
            self._overrides[override_id] = record
        audit_event = self._audit.record(
            event_type="DUAL_SIG_SUBMITTED",
            actor_id=actor_id,
            actor_role=norm_role,
            target_id=override_id,
            action="SUBMIT_DUAL_SIG_OVERRIDE",
            outcome="PENDING_CHIEF_ADMIN_COUNTERSIGN",
            http_status=201,
            detail=f"{norm_role} submitted dual-signature override {override_id} for {target_scope}.",
        )
        return {**record, "audit_event_id": audit_event["event_id"]}

    def countersign_override(
        self,
        *,
        override_id: str,
        actor_role: str,
        actor_id: str,
        decision: str,
    ) -> Dict[str, Any]:
        norm_role = normalize_role_token(actor_role)
        if norm_role != "CHIEF_ADMINISTRATOR":
            self._audit.record(
                event_type="DUAL_SIG_DENIED",
                actor_id=actor_id,
                actor_role=norm_role or "UNKNOWN",
                target_id=override_id,
                action="COUNTERSIGN_DUAL_SIG_OVERRIDE",
                outcome="DENIED_NON_CA",
                http_status=403,
                detail=f"Blocked non-Chief-Admin ({norm_role}) attempt to counter-sign override {override_id}.",
            )
            raise HTTPException(
                status_code=403,
                detail="CHIEF_ADMIN_COUNTERSIGN_REQUIRED: Only the Chief Administrator may counter-sign dual-signature overrides.",
            )
        norm_decision = decision.strip().upper()
        if norm_decision not in {"APPROVE", "VETO"}:
            raise HTTPException(status_code=422, detail="decision must be APPROVE or VETO")
        with self._lock:
            record = self._overrides.get(override_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Dual-signature override not found")
            if record["status"] != "PENDING_CHIEF_ADMIN_COUNTERSIGN":
                raise HTTPException(status_code=409, detail="Dual-signature override has already been adjudicated")
            record["status"] = "RATIFIED_EXECUTED" if norm_decision == "APPROVE" else "CHIEF_ADMIN_VETOED"
            record["countersigned_by"] = "CHIEF_ADMINISTRATOR"
            record["countersigned_at_utc"] = datetime.now(timezone.utc).isoformat()
        audit_event = self._audit.record(
            event_type="DUAL_SIG_COUNTERSIGNED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=override_id,
            action=f"COUNTERSIGN_{norm_decision}",
            outcome=record["status"],
            http_status=200,
            detail=f"Chief Administrator {norm_decision} dual-signature override {override_id}.",
        )
        return {**record, "audit_event_id": audit_event["event_id"]}

    def list_overrides(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._overrides.values()]

    def reset_normal(self) -> None:
        with self._lock:
            self.status = "NORMAL"
            self.failsafe = "ARMED"
            self.halted_by = None
            self.halted_at_utc = None
            self.halt_reason = None


_GOVERNANCE_AUDIT_LOG = GovernanceAuditLog()
_ACTIVE_HAT_GATEWAY = ActiveHatGateway(_GOVERNANCE_AUDIT_LOG)
_CA_OVERRIDE_MANAGER = CAOverrideManager(_GOVERNANCE_AUDIT_LOG)
_DIRECTIVE_R04_CONTROLLER = DirectiveR04Controller(_GOVERNANCE_AUDIT_LOG)


def get_governance_audit_log() -> GovernanceAuditLog:
    return _GOVERNANCE_AUDIT_LOG


def get_active_hat_gateway() -> ActiveHatGateway:
    return _ACTIVE_HAT_GATEWAY


def get_ca_override_manager() -> CAOverrideManager:
    return _CA_OVERRIDE_MANAGER


def get_directive_r04_controller() -> DirectiveR04Controller:
    return _DIRECTIVE_R04_CONTROLLER


def enforce_founder_immunity(
    *,
    target_id: Any,
    action: str,
    actor_role: str,
    actor_id: str = "subordinate",
) -> None:
    """Fail closed with HTTP 403 and audit entry if any subordinate targets Founder/CA."""
    if not is_founder_target(target_id):
        return
    norm_role = normalize_role_token(actor_role) or "SUBORDINATE"
    _GOVERNANCE_AUDIT_LOG.record(
        event_type="FOUNDER_IMMUNITY_BLOCK",
        actor_id=actor_id,
        actor_role=norm_role,
        target_id=str(target_id),
        action=action,
        outcome="DENIED_FOUNDER_APEX_IMMUNITY",
        http_status=403,
        detail=(
            f"Un-overridable Founder/Chief Administrator Apex immunity blocked "
            f"{norm_role} attempt to {action} target {target_id}."
        ),
    )
    raise HTTPException(
        status_code=403,
        detail=(
            f"FOUNDER_APEX_IMMUNITY_VIOLATION: {norm_role} cannot {action} "
            f"Founder/Chief Administrator identity or SCMA ({target_id})."
        ),
    )
