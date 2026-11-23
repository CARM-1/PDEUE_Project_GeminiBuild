"""
Milestone C6 — 12-House Relational Lineage Persistence, 3-Stage Dormant Bicameral
Veto Engine, Configurable FUTURE Enclave Registry & Immutable Core Guardrail.

Architectural Invariants Preserved:
- ADR-008: Strict 64-bit integer-cent accounting (zero float currency math).
- ADR-011: Zero banking credentials; opaque external references only.
- ADR-012 / Rule A14: High-Water Mark & 100% SCMA loss isolation are immutable core invariants.
- Fail-Closed Default: Governance initializes in Stage 1 (`EXECUTIVE_COMMAND`) where
  House voting/veto controls are stripped and voting endpoints return HTTP 403
  (`EXECUTIVE_COMMAND_MODE_ACTIVE`).
- Immutable Core Guardrail (ALL MODES): Proposals targeting immutable core invariants
  are permanently rejected fail-closed (`HTTP 403`, `IMMUTABLE_CORE_INVARIANT`).
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import (
    GovernanceBodyModel,
    GovernanceConfigModel,
    GovernancePetitionModel,
    GovernanceVoteModel,
    GovernanceVoterSeatModel,
    LineageHouseMemberModel,
    LineageHouseModel,
)
from app.db.session import Base, SessionLocal, engine as default_engine
from app.domain.authority_tiers import (
    get_governance_audit_log,
    is_chief_admin_role,
    is_class_t_role,
    normalize_role_token,
)

MODE_EXECUTIVE_COMMAND = "EXECUTIVE_COMMAND"
MODE_ADVISORY_PETITION_FILTER = "ADVISORY_PETITION_FILTER"
MODE_BICAMERAL_VETO_ACTIVE = "BICAMERAL_VETO_ACTIVE"

VALID_GOVERNANCE_MODES = (
    MODE_EXECUTIVE_COMMAND,
    MODE_ADVISORY_PETITION_FILTER,
    MODE_BICAMERAL_VETO_ACTIVE,
)

MODE_METADATA: Dict[str, Dict[str, Any]] = {
    MODE_EXECUTIVE_COMMAND: {
        "stage": 1,
        "label": "Stage 1 — Executive Command (Fledgling & SHTF Mode)",
        "badge_text": "Executive Command Mode Active — Voting Dormant",
        "voting_enabled": False,
        "bicameral_veto_enabled": False,
        "summary": (
            "Default fledgling and SHTF emergency mode. Voting and veto buttons are "
            "stripped from House desks and voting mutation endpoints fail closed (HTTP 403)."
        ),
    },
    MODE_ADVISORY_PETITION_FILTER: {
        "stage": 2,
        "label": "Stage 2 — Advisory Petition Filter",
        "badge_text": "Stage 2: Advisory Petition Filter Active (Founder Veto Preserved)",
        "voting_enabled": True,
        "bicameral_veto_enabled": False,
        "summary": (
            "Unlocks advisory voting (default 9-of-12 / 75% quorum -> RATIFIED_PENDING_SETTLOR). "
            "Zero unilateral execution; subject to Absolute Founder Veto (VETOED_BY_FOUNDER)."
        ),
    },
    MODE_BICAMERAL_VETO_ACTIVE: {
        "stage": 3,
        "label": "Stage 3 — Bicameral Veto Active",
        "badge_text": "Stage 3: Bicameral Veto Active (Binding Chamber Veto Enabled)",
        "voting_enabled": True,
        "bicameral_veto_enabled": True,
        "summary": (
            "Unlocks binding Bicameral Veto for authorized communal bodies and named voter seats "
            "on eligible policy and CFCP grant proposals while preserving Immutable Core Invariants "
            "and Chief Admin 1-click SHTF snap-back."
        ),
    },
}

DEFAULT_BODY_ID = "COUNCIL_OF_12_HOUSES"

IMMUTABLE_CORE_INVARIANTS: Tuple[Tuple[str, str, re.Pattern[str]], ...] = (
    (
        "87_10_3_WATERFALL",
        "87/10/3 Transaction Profit Waterfall",
        re.compile(r"(?i)\b(?:87\s*/\s*10\s*/\s*3|waterfall|tpw\s+split|profit\s+waterfall)\b"),
    ),
    (
        "ADR_012_HWM",
        "ADR-012 High-Water Mark",
        re.compile(r"(?i)\b(?:adr[\s_-]*0?12|high[\s_-]*water\s*mark|hwm)\b"),
    ),
    (
        "RULE_A14_LOSS_ISOLATION",
        "Rule A14 100% SCMA Loss Isolation",
        re.compile(r"(?i)\b(?:rule[\s_-]*a14|loss\s+isolation|socializ\w*\s+loss|absorb\s+individual\s+loss)\b"),
    ),
    (
        "QUARTER_KELLY_BOUNDS",
        "Quarter-Kelly Risk Bounds",
        re.compile(r"(?i)\b(?:quarter[\s_-]*kelly|kelly\s+bound|5%\s+(?:system\s+)?(?:risk\s+)?ceiling|risk\s+ceiling\s+override)\b"),
    ),
    (
        "FAEP_3_PERCENT",
        "3% FAEP Endowment Allocation",
        re.compile(r"(?i)\b(?:3%\s*faep|3\s*percent\s*faep|\bfaep\b|founder\s+endowment)\b"),
    ),
    (
        "ADR_011_BANKING_AIRGAP",
        "ADR-011 Banking Air-Gap & Signed Outbox",
        re.compile(
            r"(?i)\b(?:adr[\s_-]*0?11|banking\s+air[\s_-]*gap|bank\s+credentials?|routing\s+number|swift\s+code|signed\s+outbox\s+bypass)\b"
        ),
    ),
    (
        "EMERGENCY_KILL_SWITCH",
        "Directive R-04 Emergency Kill Switch",
        re.compile(r"(?i)\b(?:emergency\s+kill\s*switch|kill\s*switch|directive\s+r[\s_-]*0?4|founder\s+(?:veto\s+)?immunity|sovereign\s+immunity)\b"),
    ),
)

IMMUTABLE_CATEGORIES = frozenset(
    {
        "IMMUTABLE_CORE",
        "IMMUTABLE_INVARIANT",
        "CORE_INVARIANT",
        "WATERFALL_AMENDMENT",
        "ADR_012_AMENDMENT",
        "ADR_011_AMENDMENT",
        "KILL_SWITCH_AMENDMENT",
        "FAEP_AMENDMENT",
        "KELLY_AMENDMENT",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_cents(cents: int) -> str:
    """Format exact integer cents as USD string without floating-point arithmetic (ADR-008)."""
    val = int(cents)
    sign = "-" if val < 0 else ""
    abs_val = abs(val)
    return f"{sign}${abs_val // 100:,}.{abs_val % 100:02d}"


def validate_exact_cents(value: Any, *, field_name: str = "amount_cents") -> int:
    """Enforce ADR-008 exact 64-bit integer cents (booleans and floats fail closed)."""
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, int):
        raise HTTPException(
            status_code=422,
            detail=f"ADR-008 violation: {field_name} must be an exact non-negative integer count of cents.",
        )
    if value < 0:
        raise HTTPException(
            status_code=422,
            detail=f"ADR-008 violation: {field_name} cannot be negative.",
        )
    return int(value)


def _slugify_body_id(name: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", name.strip().upper()).strip("_")
    return slug[:48] or f"BODY_{uuid.uuid4().hex[:8].upper()}"


class EnclaveGovernanceService:
    """Relational 12-House persistence, 3-stage governance engine, and enclave registry."""

    def __init__(
        self,
        session_factory: Optional[Callable[[], Session]] = None,
        bind_engine: Any = None,
    ) -> None:
        self._lock = RLock()
        self._session_factory = session_factory or SessionLocal
        self._engine = bind_engine or default_engine
        self._initialized = False
        self._ensure_ready()

    def _ensure_ready(self) -> None:
        with self._lock:
            if self._initialized:
                try:
                    with self._session_factory() as db:
                        if db.get(GovernanceBodyModel, DEFAULT_BODY_ID) is not None:
                            return
                except Exception:
                    pass
            Base.metadata.create_all(bind=self._engine)
            with self._session_factory() as db:
                self._seed_defaults(db)
            self._initialized = True

    def _seed_defaults(self, db: Session) -> None:
        now = _utc_now()

        # 1. Global Governance Mode Config (DEFAULT: EXECUTIVE_COMMAND)
        cfg = db.get(GovernanceConfigModel, "GLOBAL")
        if cfg is None:
            db.add(
                GovernanceConfigModel(
                    config_id="GLOBAL",
                    governance_mode=MODE_EXECUTIVE_COMMAND,
                    updated_by="SYSTEM_INIT",
                    updated_at=now,
                    last_reason="Fledgling fail-closed default (Executive Command Mode)",
                )
            )

        # 2. Seed all 12 Houses (HOUSE-01..HOUSE-12) & baseline members
        for hid in range(1, 13):
            house = db.get(LineageHouseModel, hid)
            code = f"HOUSE-{hid:02d}"
            if house is None:
                if hid == 1:
                    name, leader = "House of the Founder (Vance Prime)", "Eleanor Vance"
                elif hid == 2:
                    name, leader = "House of Julian (Secondary Line)", "Julian Vance"
                else:
                    name, leader = f"House of Lineage {hid:02d}", f"Delegate {hid:02d}"
                db.add(
                    LineageHouseModel(
                        house_id=hid,
                        lineage_code=code,
                        name=name,
                        leader_name=leader,
                        leader_role="H2",
                        status="ACTIVE",
                        governance_seat=1,
                        created_at=now,
                        updated_at=now,
                    )
                )

        db.flush()

        seed_members: List[Dict[str, Any]] = [
            {
                "scma_id": "SCMA-FOUNDER_-C8575D7E",
                "house_id": 1,
                "member_id": "USR-founder_ch-C8575D7E",
                "name": "Founder Chief Admin",
                "role_tag": "Sovereign Settlor",
                "cash_cents": 500000,
                "risk_dial_bps": 200,
                "is_custodial": 0,
                "literacy_completion_pct": 100,
                "open_orders": ["KX-MIA-FRZ-32"],
            },
            {
                "scma_id": "SCMA-ELEANOR_-B2B31C9E",
                "house_id": 1,
                "member_id": "USR-eleanor_va-B2B31C9E",
                "name": "Eleanor Vance",
                "role_tag": "Designated Advisor",
                "cash_cents": 125000,
                "risk_dial_bps": 150,
                "is_custodial": 0,
                "literacy_completion_pct": 100,
                "open_orders": [],
            },
            {
                "scma_id": "SCMA-JULIAN_-A1F98B21",
                "house_id": 2,
                "member_id": "USR-julian_va-A1F98B21",
                "name": "Julian Vance",
                "role_tag": "Custodial Apprentice",
                "cash_cents": 25000,
                "risk_dial_bps": 100,
                "is_custodial": 1,
                "literacy_completion_pct": 85,
                "open_orders": ["POLY-239496"],
            },
        ]
        for hid in range(3, 13):
            code = f"HOUSE-{hid:02d}"
            seed_members.append(
                {
                    "scma_id": f"SCMA-{code}-SEED",
                    "house_id": hid,
                    "member_id": f"USR-{code}-SEED",
                    "name": f"Member {hid:02d}-A",
                    "role_tag": "Lineal Member",
                    "cash_cents": 100000,
                    "risk_dial_bps": 100,
                    "is_custodial": 0,
                    "literacy_completion_pct": 100,
                    "open_orders": [],
                }
            )

        for item in seed_members:
            if db.get(LineageHouseMemberModel, item["scma_id"]) is None:
                db.add(
                    LineageHouseMemberModel(
                        scma_id=item["scma_id"],
                        house_id=item["house_id"],
                        member_id=item["member_id"],
                        name=item["name"],
                        role_tag=item["role_tag"],
                        cash_cents=int(item["cash_cents"]),
                        high_water_mark_cents=int(item["cash_cents"]),
                        risk_dial_bps=int(item["risk_dial_bps"]),
                        baseline_risk_dial_bps=int(item["risk_dial_bps"]),
                        is_custodial=int(item["is_custodial"]),
                        status="ACTIVE",
                        literacy_completion_pct=int(item["literacy_completion_pct"]),
                        open_orders_json=json.dumps(item["open_orders"]),
                        created_at=now,
                        updated_at=now,
                    )
                )

        # 3. Seed default communal body: COUNCIL_OF_12_HOUSES (9-of-12 / 75%)
        council = db.get(GovernanceBodyModel, DEFAULT_BODY_ID)
        if council is None:
            db.add(
                GovernanceBodyModel(
                    body_id=DEFAULT_BODY_ID,
                    name="Council of 12 Houses",
                    description=(
                        "Founding bicameral lineage assembly spanning HOUSE-01 through HOUSE-12 "
                        "(default 9-of-12 / 75% quorum and veto threshold)."
                    ),
                    quorum_numerator=9,
                    quorum_denominator=12,
                    quorum_pct=75,
                    veto_threshold_count=9,
                    veto_threshold_pct=75,
                    can_exercise_stage3_veto=1,
                    active=1,
                    created_by="SYSTEM_INIT",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.flush()

        # Seed 12 House H2 office seats on COUNCIL_OF_12_HOUSES
        for hid in range(1, 13):
            seat_id = f"SEAT-HOUSE-{hid:02d}"
            if db.get(GovernanceVoterSeatModel, seat_id) is None:
                db.add(
                    GovernanceVoterSeatModel(
                        seat_id=seat_id,
                        body_id=DEFAULT_BODY_ID,
                        seat_type="HOUSE_OFFICE",
                        house_id=hid,
                        office_role="H2",
                        user_id=None,
                        display_name=f"House {hid:02d} Head (H2)",
                        can_vote=1,
                        can_veto=1,
                        active=1,
                        granted_by="SYSTEM_INIT",
                        granted_at=now,
                    )
                )

        # 4. Seed baseline petitions
        if db.get(GovernancePetitionModel, "CFCP-2026-02") is None:
            db.add(
                GovernancePetitionModel(
                    proposal_id="CFCP-2026-02",
                    body_id=DEFAULT_BODY_ID,
                    title="Apprentice Literacy Grant Petition",
                    description="Eligible CFCP grant petition supporting apprentice curriculum tools for House 02.",
                    proposal_category="CFCP_GRANT",
                    target_house_id=2,
                    amount_cents=120000,
                    status="HOUSE_VOTE_OPEN",
                    created_by="SYSTEM_INIT",
                    created_at=now,
                    updated_at=now,
                )
            )
        if db.get(GovernancePetitionModel, "PROP-2026-001") is None:
            db.add(
                GovernancePetitionModel(
                    proposal_id="PROP-2026-001",
                    body_id=DEFAULT_BODY_ID,
                    title="Quarterly CFCP Educational Grant Sweep ($500.00)",
                    description="Petition to disburse $500.00 from CFCP treasury to House 2 youth education fund.",
                    proposal_category="CFCP_GRANT",
                    target_house_id=2,
                    amount_cents=50000,
                    status="PENDING_CHIEF_ADMIN_AUTHORIZATION",
                    created_by="SYSTEM_INIT",
                    created_at="2026-09-17T03:00:00Z",
                    updated_at="2026-09-17T03:00:00Z",
                )
            )
            db.flush()
            for hid in range(1, 11):
                vid = f"VOTE-PROP-2026-001-H{hid:02d}"
                if db.get(GovernanceVoteModel, vid) is None:
                    db.add(
                        GovernanceVoteModel(
                            vote_id=vid,
                            proposal_id="PROP-2026-001",
                            body_id=DEFAULT_BODY_ID,
                            seat_id=f"SEAT-HOUSE-{hid:02d}",
                            voter_house_id=hid,
                            voter_user_id=None,
                            voter_display_name=f"House {hid:02d} Head (H2)",
                            vote_choice="AYE",
                            rationale="Historical seeded advisory vote",
                            cast_at="2026-09-17T03:00:00Z",
                        )
                    )

        db.commit()

    # ------------------------------------------------------------------
    # Relational 12-House Sync & Exact-Cent Queries
    # ------------------------------------------------------------------

    def sync_house_state(self, house_id: int, status: str, members: List[Dict[str, Any]]) -> None:
        """Persist House status and member state mutations to relational tables (ADR-008 ints)."""
        self._ensure_ready()
        now = _utc_now()
        with self._session_factory() as db:
            house = db.get(LineageHouseModel, int(house_id))
            if house is None:
                return
            house.status = str(status)
            house.updated_at = now
            for m in members:
                scma_id = str(m["scma_id"])
                row = db.get(LineageHouseMemberModel, scma_id)
                risk_bps = int(round(float(m.get("risk_dial", 0.01)) * 10_000))
                base_bps = int(round(float(m.get("baseline_risk_dial", m.get("risk_dial", 0.01))) * 10_000))
                cash_cents = int(m.get("cash_cents", 0))
                hwm_cents = int(m.get("high_water_mark_cents", cash_cents))
                orders_json = json.dumps(list(m.get("open_orders", [])))
                if row is None:
                    db.add(
                        LineageHouseMemberModel(
                            scma_id=scma_id,
                            house_id=int(house_id),
                            member_id=m.get("member_id"),
                            name=str(m.get("name", scma_id)),
                            role_tag=str(m.get("role_tag", "Lineal Member")),
                            cash_cents=cash_cents,
                            high_water_mark_cents=hwm_cents,
                            risk_dial_bps=risk_bps,
                            baseline_risk_dial_bps=base_bps,
                            is_custodial=1 if m.get("is_custodial") else 0,
                            status=str(m.get("status", "ACTIVE")),
                            literacy_completion_pct=int(m.get("literacy_completion_pct", 100)),
                            open_orders_json=orders_json,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                else:
                    row.house_id = int(house_id)
                    row.name = str(m.get("name", row.name))
                    row.role_tag = str(m.get("role_tag", row.role_tag))
                    row.cash_cents = cash_cents
                    row.high_water_mark_cents = hwm_cents
                    row.risk_dial_bps = risk_bps
                    row.baseline_risk_dial_bps = base_bps
                    row.is_custodial = 1 if m.get("is_custodial") else 0
                    row.status = str(m.get("status", row.status))
                    row.open_orders_json = orders_json
                    row.updated_at = now
            db.commit()

    def list_houses_from_db(self) -> List[Dict[str, Any]]:
        """Return all 12 Houses with exact 64-bit integer-cent rollups from SQLAlchemy."""
        self._ensure_ready()
        with self._session_factory() as db:
            houses = (
                db.query(LineageHouseModel)
                .order_by(LineageHouseModel.house_id.asc())
                .all()
            )
            result: List[Dict[str, Any]] = []
            for h in houses:
                members = (
                    db.query(LineageHouseMemberModel)
                    .filter(LineageHouseMemberModel.house_id == h.house_id)
                    .order_by(LineageHouseMemberModel.scma_id.asc())
                    .all()
                )
                total_cents = sum(int(m.cash_cents) for m in members)
                active_members = [m for m in members if m.status == "ACTIVE"]
                avg_bps = (
                    sum(int(m.risk_dial_bps) for m in active_members) // len(active_members)
                    if active_members
                    else 0
                )
                result.append(
                    {
                        "house_id": int(h.house_id),
                        "lineage_code": h.lineage_code,
                        "name": h.name,
                        "leader_name": h.leader_name,
                        "leader_role": h.leader_role,
                        "status": h.status,
                        "governance_seat": bool(h.governance_seat),
                        "member_count": len(members),
                        "total_cash_cents": int(total_cents),
                        "total_cash_formatted": format_cents(total_cents),
                        "average_risk_dial_bps": int(avg_bps),
                    }
                )
            return result

    # ------------------------------------------------------------------
    # Immutable Core Guardrail (Enforced in ALL Governance Modes)
    # ------------------------------------------------------------------

    def enforce_immutable_core_guardrail(
        self,
        *,
        title: str,
        description: str = "",
        proposal_category: str = "CFCP_GRANT",
        actor_id: str = "unknown",
        actor_role: str = "UNSPECIFIED",
    ) -> None:
        cat_norm = str(proposal_category or "").strip().upper()
        matched_label: Optional[str] = None
        matched_code: Optional[str] = None

        if cat_norm in IMMUTABLE_CATEGORIES:
            matched_code = cat_norm
            matched_label = cat_norm.replace("_", " ")
        else:
            combined = f"{title or ''} {description or ''}"
            for code, label, pattern in IMMUTABLE_CORE_INVARIANTS:
                if pattern.search(combined):
                    matched_code = code
                    matched_label = label
                    break

        if matched_code is not None:
            get_governance_audit_log().record(
                event_type="IMMUTABLE_CORE_INVARIANT_BLOCK",
                actor_id=str(actor_id or "unknown"),
                actor_role=normalize_role_token(actor_role) or "UNSPECIFIED",
                target_id=matched_code,
                action="PROPOSE_IMMUTABLE_CORE_CHANGE",
                outcome="DENIED_IMMUTABLE_CORE_INVARIANT",
                http_status=403,
                detail=(
                    f"Rejected proposal targeting immutable core invariant '{matched_label}' "
                    f"(title={title!r}). Protected in all governance modes."
                ),
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    f"IMMUTABLE_CORE_INVARIANT: Proposals targeting '{matched_label}' "
                    "are permanently prohibited in all governance modes."
                ),
            )

    # ------------------------------------------------------------------
    # Chief Administrator Authorization Helper
    # ------------------------------------------------------------------

    def _require_chief_admin(
        self,
        *,
        actor_role: Optional[str],
        actor_id: str,
        action: str,
        target_id: str = "GOVERNANCE",
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
                detail=f"Role '{norm or 'UNSPECIFIED'}' is prohibited from executing {action}.",
            )
            raise HTTPException(
                status_code=403,
                detail=f"CHIEF_ADMIN_REQUIRED: Only the Chief Administrator / Founder may execute {action}.",
            )

    # ------------------------------------------------------------------
    # 3-Stage Governance Mode & 1-Click SHTF Snap-Back
    # ------------------------------------------------------------------

    def get_governance_mode(self) -> Dict[str, Any]:
        self._ensure_ready()
        with self._session_factory() as db:
            cfg = db.get(GovernanceConfigModel, "GLOBAL")
            mode = cfg.governance_mode if cfg else MODE_EXECUTIVE_COMMAND
            if mode not in MODE_METADATA:
                mode = MODE_EXECUTIVE_COMMAND
            meta = MODE_METADATA[mode]
            return {
                "governance_mode": mode,
                "stage": meta["stage"],
                "label": meta["label"],
                "badge_text": meta["badge_text"],
                "voting_enabled": meta["voting_enabled"],
                "bicameral_veto_enabled": meta["bicameral_veto_enabled"],
                "summary": meta["summary"],
                "updated_by": cfg.updated_by if cfg else "SYSTEM_INIT",
                "updated_at": cfg.updated_at if cfg else _utc_now(),
                "last_reason": cfg.last_reason if cfg else "",
            }

    def set_governance_mode(
        self,
        *,
        governance_mode: str,
        actor_role: Optional[str],
        actor_id: str = "USR-founder_ch-C8575D7E",
        reason: str = "",
        is_shtf_snapback: bool = False,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        action = "SHTF_SNAPBACK" if is_shtf_snapback else "SET_GOVERNANCE_MODE"
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action=action,
            target_id=str(governance_mode),
        )
        mode_norm = str(governance_mode or "").strip().upper()
        if mode_norm not in VALID_GOVERNANCE_MODES:
            raise HTTPException(
                status_code=422,
                detail=f"governance_mode must be one of {', '.join(VALID_GOVERNANCE_MODES)}",
            )

        now = _utc_now()
        with self._session_factory() as db:
            cfg = db.get(GovernanceConfigModel, "GLOBAL")
            previous_mode = cfg.governance_mode if cfg else MODE_EXECUTIVE_COMMAND
            if cfg is None:
                cfg = GovernanceConfigModel(
                    config_id="GLOBAL",
                    governance_mode=mode_norm,
                    updated_by=actor_id,
                    updated_at=now,
                    last_reason=reason.strip() or ("SHTF Emergency Snap-Back" if is_shtf_snapback else ""),
                )
                db.add(cfg)
            else:
                cfg.governance_mode = mode_norm
                cfg.updated_by = actor_id
                cfg.updated_at = now
                cfg.last_reason = reason.strip() or ("SHTF Emergency Snap-Back" if is_shtf_snapback else "")
            db.commit()

        event_type = "GOVERNANCE_SHTF_SNAPBACK" if is_shtf_snapback else "GOVERNANCE_MODE_CHANGED"
        audit = get_governance_audit_log().record(
            event_type=event_type,
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=mode_norm,
            action=action,
            outcome=f"{previous_mode}->{mode_norm}",
            http_status=200,
            detail=(
                f"Governance mode transitioned {previous_mode} -> {mode_norm}. "
                f"Reason: {reason.strip() or 'Chief Administrator determination'}"
            ),
            metadata={"previous_mode": previous_mode, "new_mode": mode_norm, "shtf_snapback": is_shtf_snapback},
        )
        state = self.get_governance_mode()
        return {
            **state,
            "previous_mode": previous_mode,
            "shtf_snapback": is_shtf_snapback,
            "audit_event_id": audit["event_id"],
        }

    # ------------------------------------------------------------------
    # Configurable FUTURE Enclave Bodies & Named Voter Seats
    # ------------------------------------------------------------------

    def _serialize_seat(self, seat: GovernanceVoterSeatModel) -> Dict[str, Any]:
        return {
            "seat_id": seat.seat_id,
            "body_id": seat.body_id,
            "seat_type": seat.seat_type,
            "house_id": seat.house_id,
            "house_code": f"HOUSE-{seat.house_id:02d}" if seat.house_id else None,
            "office_role": seat.office_role,
            "user_id": seat.user_id,
            "display_name": seat.display_name,
            "can_vote": bool(seat.can_vote),
            "can_veto": bool(seat.can_veto),
            "active": bool(seat.active),
            "granted_by": seat.granted_by,
            "granted_at": seat.granted_at,
            "revoked_by": seat.revoked_by,
            "revoked_at": seat.revoked_at,
        }

    def _serialize_body(self, body: GovernanceBodyModel, seats: List[GovernanceVoterSeatModel]) -> Dict[str, Any]:
        serialized_seats = [self._serialize_seat(s) for s in seats]
        active_seats = [s for s in serialized_seats if s["active"]]
        veto_seats = [s for s in active_seats if s["can_veto"]]
        return {
            "body_id": body.body_id,
            "name": body.name,
            "description": body.description,
            "quorum_numerator": int(body.quorum_numerator),
            "quorum_denominator": int(body.quorum_denominator),
            "quorum_pct": int(body.quorum_pct),
            "veto_threshold_count": int(body.veto_threshold_count),
            "veto_threshold_pct": int(body.veto_threshold_pct),
            "can_exercise_stage3_veto": bool(body.can_exercise_stage3_veto),
            "active": bool(body.active),
            "active_seat_count": len(active_seats),
            "active_veto_seat_count": len(veto_seats),
            "seats": serialized_seats,
            "created_by": body.created_by,
            "created_at": body.created_at,
            "updated_at": body.updated_at,
        }

    def list_bodies(self) -> List[Dict[str, Any]]:
        self._ensure_ready()
        with self._session_factory() as db:
            bodies = db.query(GovernanceBodyModel).order_by(GovernanceBodyModel.created_at.asc()).all()
            out: List[Dict[str, Any]] = []
            for body in bodies:
                seats = (
                    db.query(GovernanceVoterSeatModel)
                    .filter(GovernanceVoterSeatModel.body_id == body.body_id)
                    .order_by(GovernanceVoterSeatModel.seat_id.asc())
                    .all()
                )
                out.append(self._serialize_body(body, seats))
            return out

    def create_body(
        self,
        *,
        name: str,
        description: str = "",
        quorum_numerator: int = 2,
        quorum_denominator: int = 3,
        quorum_pct: Optional[int] = None,
        veto_threshold_count: int = 2,
        veto_threshold_pct: Optional[int] = None,
        can_exercise_stage3_veto: bool = True,
        body_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        actor_id: str = "USR-founder_ch-C8575D7E",
    ) -> Dict[str, Any]:
        self._ensure_ready()
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="CREATE_GOVERNANCE_BODY",
            target_id=name,
        )
        clean_name = " ".join(str(name or "").strip().split())
        if not clean_name:
            raise HTTPException(status_code=422, detail="Body name is required.")
        q_num = max(1, int(quorum_numerator))
        q_den = max(q_num, int(quorum_denominator))
        q_pct = int(quorum_pct) if quorum_pct is not None else max(1, min(100, (q_num * 100) // q_den))
        v_cnt = max(1, int(veto_threshold_count))
        v_pct = int(veto_threshold_pct) if veto_threshold_pct is not None else max(1, min(100, (v_cnt * 100) // max(v_cnt, q_den)))
        resolved_id = _slugify_body_id(body_id or clean_name)
        now = _utc_now()

        with self._session_factory() as db:
            if db.query(GovernanceBodyModel).filter(GovernanceBodyModel.name == clean_name).first():
                raise HTTPException(status_code=409, detail=f"Governance body '{clean_name}' already exists.")
            if db.get(GovernanceBodyModel, resolved_id) is not None:
                resolved_id = f"{resolved_id}_{uuid.uuid4().hex[:6].upper()}"
            body = GovernanceBodyModel(
                body_id=resolved_id,
                name=clean_name,
                description=str(description or "").strip(),
                quorum_numerator=q_num,
                quorum_denominator=q_den,
                quorum_pct=q_pct,
                veto_threshold_count=v_cnt,
                veto_threshold_pct=v_pct,
                can_exercise_stage3_veto=1 if can_exercise_stage3_veto else 0,
                active=1,
                created_by=actor_id,
                created_at=now,
                updated_at=now,
            )
            db.add(body)
            db.commit()
            db.refresh(body)
            serialized = self._serialize_body(body, [])

        audit = get_governance_audit_log().record(
            event_type="GOVERNANCE_BODY_CREATED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=resolved_id,
            action="CREATE_GOVERNANCE_BODY",
            outcome="CREATED",
            http_status=201,
            detail=f"Created communal enclave body '{clean_name}' (quorum {q_num}/{q_den}, veto threshold {v_cnt}).",
        )
        return {**serialized, "audit_event_id": audit["event_id"]}

    def update_body(
        self,
        body_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        quorum_numerator: Optional[int] = None,
        quorum_denominator: Optional[int] = None,
        quorum_pct: Optional[int] = None,
        veto_threshold_count: Optional[int] = None,
        veto_threshold_pct: Optional[int] = None,
        can_exercise_stage3_veto: Optional[bool] = None,
        active: Optional[bool] = None,
        actor_role: Optional[str] = None,
        actor_id: str = "USR-founder_ch-C8575D7E",
    ) -> Dict[str, Any]:
        self._ensure_ready()
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="UPDATE_GOVERNANCE_BODY",
            target_id=body_id,
        )
        now = _utc_now()
        with self._session_factory() as db:
            body = db.get(GovernanceBodyModel, body_id)
            if body is None:
                raise HTTPException(status_code=404, detail=f"Governance body '{body_id}' not found.")
            if name is not None:
                clean_name = " ".join(str(name).strip().split())
                if not clean_name:
                    raise HTTPException(status_code=422, detail="Body name cannot be empty.")
                dup = (
                    db.query(GovernanceBodyModel)
                    .filter(GovernanceBodyModel.name == clean_name, GovernanceBodyModel.body_id != body_id)
                    .first()
                )
                if dup is not None:
                    raise HTTPException(status_code=409, detail=f"Governance body '{clean_name}' already exists.")
                body.name = clean_name
            if description is not None:
                body.description = str(description).strip()
            if quorum_numerator is not None:
                body.quorum_numerator = max(1, int(quorum_numerator))
            if quorum_denominator is not None:
                body.quorum_denominator = max(body.quorum_numerator, int(quorum_denominator))
            if quorum_pct is not None:
                body.quorum_pct = max(1, min(100, int(quorum_pct)))
            if veto_threshold_count is not None:
                body.veto_threshold_count = max(1, int(veto_threshold_count))
            if veto_threshold_pct is not None:
                body.veto_threshold_pct = max(1, min(100, int(veto_threshold_pct)))
            if can_exercise_stage3_veto is not None:
                body.can_exercise_stage3_veto = 1 if can_exercise_stage3_veto else 0
            if active is not None:
                body.active = 1 if active else 0
            body.updated_at = now
            db.commit()
            seats = (
                db.query(GovernanceVoterSeatModel)
                .filter(GovernanceVoterSeatModel.body_id == body_id)
                .order_by(GovernanceVoterSeatModel.seat_id.asc())
                .all()
            )
            serialized = self._serialize_body(body, seats)

        audit = get_governance_audit_log().record(
            event_type="GOVERNANCE_BODY_UPDATED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=body_id,
            action="UPDATE_GOVERNANCE_BODY",
            outcome="UPDATED",
            http_status=200,
            detail=f"Updated communal enclave body '{serialized['name']}'.",
        )
        return {**serialized, "audit_event_id": audit["event_id"]}

    def list_voter_seats(self, body_id: str) -> List[Dict[str, Any]]:
        self._ensure_ready()
        with self._session_factory() as db:
            if db.get(GovernanceBodyModel, body_id) is None:
                raise HTTPException(status_code=404, detail=f"Governance body '{body_id}' not found.")
            seats = (
                db.query(GovernanceVoterSeatModel)
                .filter(GovernanceVoterSeatModel.body_id == body_id)
                .order_by(GovernanceVoterSeatModel.seat_id.asc())
                .all()
            )
            return [self._serialize_seat(s) for s in seats]

    def grant_voter_seat(
        self,
        body_id: str,
        *,
        seat_type: str = "NAMED_INDIVIDUAL",
        display_name: str,
        user_id: Optional[str] = None,
        house_id: Optional[int] = None,
        office_role: Optional[str] = None,
        can_vote: bool = True,
        can_veto: bool = False,
        actor_role: Optional[str] = None,
        actor_id: str = "USR-founder_ch-C8575D7E",
    ) -> Dict[str, Any]:
        self._ensure_ready()
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="GRANT_VOTER_SEAT",
            target_id=f"{body_id}:{user_id or house_id or display_name}",
        )
        stype = str(seat_type or "NAMED_INDIVIDUAL").strip().upper()
        if stype not in {"HOUSE_OFFICE", "NAMED_INDIVIDUAL"}:
            raise HTTPException(status_code=422, detail="seat_type must be HOUSE_OFFICE or NAMED_INDIVIDUAL")
        clean_name = " ".join(str(display_name or "").strip().split())
        if not clean_name:
            raise HTTPException(status_code=422, detail="display_name is required.")

        if stype == "NAMED_INDIVIDUAL":
            clean_uid = str(user_id or "").strip()
            if not clean_uid:
                raise HTTPException(status_code=422, detail="user_id is required for NAMED_INDIVIDUAL voter seats.")
            resolved_house_id = int(house_id) if house_id is not None else None
            resolved_office = office_role.strip().upper() if office_role else None
        else:
            if house_id is None or int(house_id) not in range(1, 13):
                raise HTTPException(status_code=422, detail="house_id (1..12) is required for HOUSE_OFFICE voter seats.")
            resolved_house_id = int(house_id)
            resolved_office = str(office_role or "H2").strip().upper()
            clean_uid = None

        now = _utc_now()
        seat_id = f"SEAT-{uuid.uuid4().hex[:10].upper()}"
        with self._session_factory() as db:
            body = db.get(GovernanceBodyModel, body_id)
            if body is None:
                raise HTTPException(status_code=404, detail=f"Governance body '{body_id}' not found.")
            seat = GovernanceVoterSeatModel(
                seat_id=seat_id,
                body_id=body_id,
                seat_type=stype,
                house_id=resolved_house_id,
                office_role=resolved_office,
                user_id=clean_uid,
                display_name=clean_name,
                can_vote=1 if can_vote else 0,
                can_veto=1 if can_veto else 0,
                active=1,
                granted_by=actor_id,
                granted_at=now,
            )
            db.add(seat)
            db.commit()
            db.refresh(seat)
            serialized = self._serialize_seat(seat)

        audit = get_governance_audit_log().record(
            event_type="GOVERNANCE_SEAT_GRANTED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=seat_id,
            action="GRANT_VOTER_SEAT",
            outcome="GRANTED",
            http_status=201,
            detail=(
                f"Granted {stype} seat '{clean_name}' on body '{body_id}' "
                f"(can_vote={bool(can_vote)}, can_veto={bool(can_veto)})."
            ),
            metadata={"body_id": body_id, "seat_type": stype, "user_id": clean_uid, "house_id": resolved_house_id},
        )
        return {**serialized, "audit_event_id": audit["event_id"]}

    def revoke_voter_seat(
        self,
        seat_id: str,
        *,
        reason: str = "",
        actor_role: Optional[str] = None,
        actor_id: str = "USR-founder_ch-C8575D7E",
    ) -> Dict[str, Any]:
        self._ensure_ready()
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="REVOKE_VOTER_SEAT",
            target_id=seat_id,
        )
        now = _utc_now()
        with self._session_factory() as db:
            seat = db.get(GovernanceVoterSeatModel, seat_id)
            if seat is None:
                raise HTTPException(status_code=404, detail=f"Voter seat '{seat_id}' not found.")
            seat.active = 0
            seat.revoked_by = actor_id
            seat.revoked_at = now
            db.commit()
            db.refresh(seat)
            serialized = self._serialize_seat(seat)

        audit = get_governance_audit_log().record(
            event_type="GOVERNANCE_SEAT_REVOKED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=seat_id,
            action="REVOKE_VOTER_SEAT",
            outcome="REVOKED",
            http_status=200,
            detail=f"Revoked voter seat '{serialized['display_name']}' ({seat_id}). Reason: {reason.strip() or 'Chief Administrator determination'}",
        )
        return {**serialized, "audit_event_id": audit["event_id"]}

    # ------------------------------------------------------------------
    # Petitions, Mode-Gated Voting & Bicameral Veto / Founder Adjudication
    # ------------------------------------------------------------------

    def _serialize_petition(
        self,
        petition: GovernancePetitionModel,
        body: Optional[GovernanceBodyModel],
        votes: List[GovernanceVoteModel],
    ) -> Dict[str, Any]:
        aye_votes = [v for v in votes if v.vote_choice == "AYE"]
        nay_votes = [v for v in votes if v.vote_choice == "NAY"]
        veto_votes = [v for v in votes if v.vote_choice == "VETO"]
        aye_houses = sorted({int(v.voter_house_id) for v in aye_votes if v.voter_house_id is not None})
        nay_houses = sorted({int(v.voter_house_id) for v in nay_votes if v.voter_house_id is not None})
        veto_houses = sorted({int(v.voter_house_id) for v in veto_votes if v.voter_house_id is not None})
        quorum_req = int(body.quorum_numerator) if body else 9
        quorum_den = int(body.quorum_denominator) if body else 12
        veto_req = int(body.veto_threshold_count) if body else 9
        return {
            "proposal_id": petition.proposal_id,
            "body_id": petition.body_id,
            "body_name": body.name if body else petition.body_id,
            "title": petition.title,
            "description": petition.description,
            "proposal_category": petition.proposal_category,
            "target_house_id": int(petition.target_house_id),
            "amount_cents": int(petition.amount_cents),
            "amount_formatted": format_cents(int(petition.amount_cents)),
            "status": petition.status,
            "aye_count": len(aye_votes),
            "nay_count": len(nay_votes),
            "veto_count": len(veto_votes),
            "aye_house_ids": aye_houses,
            "nay_house_ids": nay_houses,
            "veto_house_ids": veto_houses,
            "affirmative_house_ids": aye_houses,
            "house_ratified": len(aye_votes) >= quorum_req,
            "threshold": quorum_req,
            "quorum_numerator": quorum_req,
            "quorum_denominator": quorum_den,
            "veto_threshold_count": veto_req,
            "votes": [
                {
                    "vote_id": v.vote_id,
                    "seat_id": v.seat_id,
                    "voter_house_id": v.voter_house_id,
                    "voter_user_id": v.voter_user_id,
                    "voter_display_name": v.voter_display_name,
                    "vote_choice": v.vote_choice,
                    "rationale": v.rationale,
                    "cast_at": v.cast_at,
                }
                for v in votes
            ],
            "created_by": petition.created_by,
            "settled_by": petition.settled_by,
            "settled_at": petition.settled_at,
            "veto_reason": petition.veto_reason,
            "created_at": petition.created_at,
            "updated_at": petition.updated_at,
        }

    def list_petitions(self, body_id: Optional[str] = None) -> List[Dict[str, Any]]:
        self._ensure_ready()
        with self._session_factory() as db:
            query = db.query(GovernancePetitionModel)
            if body_id:
                query = query.filter(GovernancePetitionModel.body_id == body_id)
            petitions = query.order_by(GovernancePetitionModel.created_at.desc()).all()
            out: List[Dict[str, Any]] = []
            for p in petitions:
                body = db.get(GovernanceBodyModel, p.body_id)
                votes = (
                    db.query(GovernanceVoteModel)
                    .filter(GovernanceVoteModel.proposal_id == p.proposal_id)
                    .order_by(GovernanceVoteModel.cast_at.asc())
                    .all()
                )
                out.append(self._serialize_petition(p, body, votes))
            return out

    def get_petition(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_ready()
        with self._session_factory() as db:
            p = db.get(GovernancePetitionModel, proposal_id)
            if p is None:
                return None
            body = db.get(GovernanceBodyModel, p.body_id)
            votes = (
                db.query(GovernanceVoteModel)
                .filter(GovernanceVoteModel.proposal_id == p.proposal_id)
                .order_by(GovernanceVoteModel.cast_at.asc())
                .all()
            )
            return self._serialize_petition(p, body, votes)

    def create_petition(
        self,
        *,
        title: str,
        description: str = "",
        body_id: str = DEFAULT_BODY_ID,
        proposal_category: str = "CFCP_GRANT",
        target_house_id: int = 1,
        amount_cents: int = 0,
        actor_role: Optional[str] = None,
        actor_id: str = "HOUSE_DELEGATE",
        proposal_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_ready()

        # 1. Immutable Core Guardrail (ALL MODES — permanently rejected HTTP 403)
        self.enforce_immutable_core_guardrail(
            title=title,
            description=description,
            proposal_category=proposal_category,
            actor_id=actor_id,
            actor_role=actor_role or "UNSPECIFIED",
        )

        # 2. Class T & H1 isolation
        norm_role = normalize_role_token(actor_role)
        if is_class_t_role(actor_role):
            get_governance_audit_log().record(
                event_type="ROLE_BOUNDARY_DENIED",
                actor_id=actor_id,
                actor_role=norm_role or "CLASS_T",
                target_id=body_id,
                action="CREATE_PETITION",
                outcome="DENIED_CLASS_T_ZERO_HOUSE_AUTHORITY",
                http_status=403,
                detail="Class T technical roles are hard-blocked from all House governance actions.",
            )
            raise HTTPException(status_code=403, detail="Class T technical roles have zero House governance authority.")
        if norm_role == "H1":
            get_governance_audit_log().record(
                event_type="ROLE_BOUNDARY_DENIED",
                actor_id=actor_id,
                actor_role="H1",
                target_id=body_id,
                action="CREATE_PETITION",
                outcome="DENIED_H1_NON_VOTING",
                http_status=403,
                detail="H1 secretarial role has zero petition submission authority.",
            )
            raise HTTPException(status_code=403, detail="H1 secretarial role has no governance petition authority.")

        # 3. 3-Stage Governance Mode Gate
        mode_state = self.get_governance_mode()
        if mode_state["governance_mode"] == MODE_EXECUTIVE_COMMAND:
            get_governance_audit_log().record(
                event_type="GOVERNANCE_MODE_BLOCKED",
                actor_id=actor_id,
                actor_role=norm_role or "UNSPECIFIED",
                target_id=body_id,
                action="CREATE_PETITION",
                outcome="DENIED_EXECUTIVE_COMMAND_MODE_ACTIVE",
                http_status=403,
                detail="Petition creation blocked while Stage 1 EXECUTIVE_COMMAND mode is active.",
            )
            raise HTTPException(
                status_code=403,
                detail="EXECUTIVE_COMMAND_MODE_ACTIVE: Voting and petition submission are dormant in Stage 1 Executive Command mode.",
            )

        # 4. Validate ADR-008 integer cents & fields
        cents = validate_exact_cents(amount_cents, field_name="amount_cents")
        clean_title = " ".join(str(title or "").strip().split())
        if not clean_title:
            raise HTTPException(status_code=422, detail="Proposal title is required.")
        if int(target_house_id) not in range(1, 13):
            raise HTTPException(status_code=422, detail="target_house_id must be between 1 and 12.")

        now = _utc_now()
        pid = proposal_id or f"PROP-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:6].upper()}"
        with self._session_factory() as db:
            body = db.get(GovernanceBodyModel, body_id)
            if body is None or not body.active:
                raise HTTPException(status_code=404, detail=f"Active governance body '{body_id}' not found.")
            petition = GovernancePetitionModel(
                proposal_id=pid,
                body_id=body_id,
                title=clean_title,
                description=str(description or "").strip(),
                proposal_category=str(proposal_category or "CFCP_GRANT").strip().upper(),
                target_house_id=int(target_house_id),
                amount_cents=cents,
                status="HOUSE_VOTE_OPEN",
                created_by=actor_id,
                created_at=now,
                updated_at=now,
            )
            db.add(petition)
            db.commit()
            db.refresh(petition)
            serialized = self._serialize_petition(petition, body, [])

        audit = get_governance_audit_log().record(
            event_type="GOVERNANCE_PETITION_CREATED",
            actor_id=actor_id,
            actor_role=norm_role or "HOUSE_DELEGATE",
            target_id=pid,
            action="CREATE_PETITION",
            outcome="CREATED",
            http_status=201,
            detail=f"Created petition '{clean_title}' ({pid}) under {body_id} for {format_cents(cents)}.",
        )
        return {**serialized, "audit_event_id": audit["event_id"]}

    def cast_vote(
        self,
        *,
        proposal_id: str,
        vote_choice: str,
        actor_role: Optional[str] = None,
        actor_id: str = "",
        house_id: Optional[int] = None,
        user_id: Optional[str] = None,
        seat_id: Optional[str] = None,
        rationale: str = "",
    ) -> Dict[str, Any]:
        self._ensure_ready()
        norm_role = normalize_role_token(actor_role)

        # 1. Hard-block Class T and H1
        if is_class_t_role(actor_role):
            get_governance_audit_log().record(
                event_type="ROLE_BOUNDARY_DENIED",
                actor_id=actor_id or str(user_id or "CLASS_T"),
                actor_role=norm_role or "CLASS_T",
                target_id=proposal_id,
                action="CAST_GOVERNANCE_VOTE",
                outcome="DENIED_CLASS_T_ZERO_HOUSE_AUTHORITY",
                http_status=403,
                detail="Class T technical roles are hard-blocked from all House governance actions.",
            )
            raise HTTPException(status_code=403, detail="Class T technical roles have zero House governance authority.")

        if norm_role == "H1":
            get_governance_audit_log().record(
                event_type="ROLE_BOUNDARY_DENIED",
                actor_id=actor_id or f"HOUSE-{house_id or 0:02d}:H1",
                actor_role="H1",
                target_id=proposal_id,
                action="CAST_GOVERNANCE_VOTE",
                outcome="DENIED_H1_NON_VOTING",
                http_status=403,
                detail="H1 secretarial role has zero voting or veto authority.",
            )
            raise HTTPException(status_code=403, detail="H1 secretarial role has no voting authority.")

        # 2. Enforce 3-Stage Governance Mode Gate
        mode_state = self.get_governance_mode()
        active_mode = mode_state["governance_mode"]
        if active_mode == MODE_EXECUTIVE_COMMAND:
            get_governance_audit_log().record(
                event_type="GOVERNANCE_MODE_BLOCKED",
                actor_id=actor_id or str(user_id or f"HOUSE-{house_id or 0:02d}"),
                actor_role=norm_role or "H2",
                target_id=proposal_id,
                action="CAST_GOVERNANCE_VOTE",
                outcome="DENIED_EXECUTIVE_COMMAND_MODE_ACTIVE",
                http_status=403,
                detail="Voting blocked while Stage 1 EXECUTIVE_COMMAND mode is active.",
            )
            raise HTTPException(
                status_code=403,
                detail="EXECUTIVE_COMMAND_MODE_ACTIVE: Voting and bicameral veto are dormant in Stage 1 Executive Command mode.",
            )

        choice = str(vote_choice or "").strip().upper()
        if choice not in {"AYE", "NAY", "VETO"}:
            raise HTTPException(status_code=422, detail="vote must be AYE, NAY, or VETO")

        if choice == "VETO" and active_mode != MODE_BICAMERAL_VETO_ACTIVE:
            get_governance_audit_log().record(
                event_type="GOVERNANCE_VETO_BLOCKED",
                actor_id=actor_id or str(user_id or f"HOUSE-{house_id or 0:02d}"),
                actor_role=norm_role or "H2",
                target_id=proposal_id,
                action="CAST_BICAMERAL_VETO",
                outcome="DENIED_STAGE_3_REQUIRED",
                http_status=403,
                detail="Binding Bicameral Veto requires Stage 3 BICAMERAL_VETO_ACTIVE mode.",
            )
            raise HTTPException(
                status_code=403,
                detail="STAGE_3_REQUIRED_FOR_BICAMERAL_VETO: Binding Bicameral Veto is only available in Stage 3 (BICAMERAL_VETO_ACTIVE).",
            )

        now = _utc_now()
        with self._session_factory() as db:
            petition = db.get(GovernancePetitionModel, proposal_id)
            if petition is None:
                raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")

            # Defense-in-depth: Immutable Core Guardrail
            self.enforce_immutable_core_guardrail(
                title=petition.title,
                description=petition.description,
                proposal_category=petition.proposal_category,
                actor_id=actor_id or str(user_id or house_id or "voter"),
                actor_role=norm_role or "H2",
            )

            if petition.status in {"SOVEREIGN_EXECUTED", "VETOED_BY_FOUNDER", "VETOED_BY_BICAMERAL_CHAMBER"}:
                raise HTTPException(
                    status_code=409,
                    detail=f"Proposal '{proposal_id}' is already closed with status {petition.status}.",
                )

            body = db.get(GovernanceBodyModel, petition.body_id)
            if body is None or not body.active:
                raise HTTPException(status_code=403, detail="Associated governance body is inactive.")

            # Resolve active voter seat
            seat_query = db.query(GovernanceVoterSeatModel).filter(
                GovernanceVoterSeatModel.body_id == petition.body_id,
                GovernanceVoterSeatModel.active == 1,
            )
            seat: Optional[GovernanceVoterSeatModel] = None
            if seat_id:
                seat = seat_query.filter(GovernanceVoterSeatModel.seat_id == seat_id).first()
            elif user_id:
                seat = seat_query.filter(GovernanceVoterSeatModel.user_id == user_id).first()
            elif house_id is not None:
                seat = seat_query.filter(
                    GovernanceVoterSeatModel.seat_type == "HOUSE_OFFICE",
                    GovernanceVoterSeatModel.house_id == int(house_id),
                ).first()

            if seat is None or not seat.can_vote:
                get_governance_audit_log().record(
                    event_type="GOVERNANCE_VOTE_DENIED",
                    actor_id=actor_id or str(user_id or f"HOUSE-{house_id or 0:02d}"),
                    actor_role=norm_role or "VOTER",
                    target_id=proposal_id,
                    action="CAST_GOVERNANCE_VOTE",
                    outcome="DENIED_SEAT_NOT_ACTIVE_OR_UNAUTHORIZED",
                    http_status=403,
                    detail=f"Voter has no active seat on body '{petition.body_id}'.",
                )
                raise HTTPException(
                    status_code=403,
                    detail="VOTER_SEAT_NOT_ACTIVE_OR_UNAUTHORIZED: Voter does not hold an active voting seat in this communal body.",
                )

            if choice == "VETO":
                if not body.can_exercise_stage3_veto or not seat.can_veto:
                    get_governance_audit_log().record(
                        event_type="GOVERNANCE_VETO_BLOCKED",
                        actor_id=actor_id or seat.user_id or seat.seat_id,
                        actor_role=norm_role or seat.office_role or "VOTER",
                        target_id=proposal_id,
                        action="CAST_BICAMERAL_VETO",
                        outcome="DENIED_VETO_RIGHT_NOT_GRANTED",
                        http_status=403,
                        detail=f"Seat '{seat.display_name}' ({seat.seat_id}) lacks Stage 3 veto privilege.",
                    )
                    raise HTTPException(
                        status_code=403,
                        detail="VETO_RIGHT_NOT_GRANTED: This voter seat or communal body is not authorized to cast a binding Stage 3 veto.",
                    )

            # Upsert ballot for this seat on this proposal
            existing_vote = (
                db.query(GovernanceVoteModel)
                .filter(
                    GovernanceVoteModel.proposal_id == proposal_id,
                    GovernanceVoteModel.seat_id == seat.seat_id,
                )
                .first()
            )
            if existing_vote is not None:
                existing_vote.vote_choice = choice
                existing_vote.rationale = str(rationale or "").strip()
                existing_vote.cast_at = now
            else:
                db.add(
                    GovernanceVoteModel(
                        vote_id=f"VOTE-{uuid.uuid4().hex[:10].upper()}",
                        proposal_id=proposal_id,
                        body_id=petition.body_id,
                        seat_id=seat.seat_id,
                        voter_house_id=seat.house_id if seat.house_id is not None else house_id,
                        voter_user_id=seat.user_id or user_id,
                        voter_display_name=seat.display_name,
                        vote_choice=choice,
                        rationale=str(rationale or "").strip(),
                        cast_at=now,
                    )
                )
            db.flush()

            all_votes = (
                db.query(GovernanceVoteModel)
                .filter(GovernanceVoteModel.proposal_id == proposal_id)
                .order_by(GovernanceVoteModel.cast_at.asc())
                .all()
            )
            aye_count = sum(1 for v in all_votes if v.vote_choice == "AYE")
            nay_count = sum(1 for v in all_votes if v.vote_choice == "NAY")
            veto_count = sum(1 for v in all_votes if v.vote_choice == "VETO")

            if active_mode == MODE_BICAMERAL_VETO_ACTIVE and veto_count >= int(body.veto_threshold_count):
                petition.status = "VETOED_BY_BICAMERAL_CHAMBER"
                petition.settled_by = f"CHAMBER:{body.body_id}"
                petition.settled_at = now
                petition.veto_reason = (
                    rationale.strip()
                    or f"Binding Stage 3 Bicameral Veto enacted by {body.name} ({veto_count}/{body.veto_threshold_count})."
                )
                effect = "BINDING_BICAMERAL_VETO"
            elif aye_count >= int(body.quorum_numerator):
                petition.status = "RATIFIED_PENDING_SETTLOR"
                effect = "ADVISORY_PETITION_ONLY" if active_mode == MODE_ADVISORY_PETITION_FILTER else "BICAMERAL_CHAMBER_ACTIVE"
            else:
                petition.status = "HOUSE_VOTE_OPEN"
                effect = "ADVISORY_PETITION_ONLY" if active_mode == MODE_ADVISORY_PETITION_FILTER else "BICAMERAL_CHAMBER_ACTIVE"

            petition.updated_at = now
            resolved_seat_id = str(seat.seat_id)
            seat_display_name = str(seat.display_name)
            seat_office_role = str(seat.office_role or "VOTER")
            db.commit()
            serialized = self._serialize_petition(petition, body, all_votes)

        audit_event_type = (
            "GOVERNANCE_BICAMERAL_VETO_ENACTED"
            if serialized["status"] == "VETOED_BY_BICAMERAL_CHAMBER"
            else "GOVERNANCE_VOTE_CAST"
        )
        audit = get_governance_audit_log().record(
            event_type=audit_event_type,
            actor_id=actor_id or str(user_id or f"HOUSE-{house_id or 0:02d}"),
            actor_role=norm_role or seat_office_role,
            target_id=proposal_id,
            action=f"CAST_VOTE_{choice}",
            outcome=serialized["status"],
            http_status=200,
            detail=(
                f"{seat_display_name} cast {choice} on {proposal_id} in {active_mode}. "
                f"Tallies: AYE={aye_count}, NAY={nay_count}, VETO={veto_count} -> {serialized['status']}."
            ),
        )
        return {
            **serialized,
            "house_vote": choice,
            "vote_choice": choice,
            "seat_id": resolved_seat_id,
            "governance_mode": active_mode,
            "effect": effect,
            "audit_event_id": audit["event_id"],
        }

    def adjudicate_petition(
        self,
        *,
        proposal_id: str,
        action: str,
        actor_role: Optional[str],
        actor_id: str = "SCMA-FOUNDER_-C8575D7E",
        reason: str = "",
    ) -> Dict[str, Any]:
        self._ensure_ready()
        self._require_chief_admin(
            actor_role=actor_role,
            actor_id=actor_id,
            action="ADJUDICATE_PETITION",
            target_id=proposal_id,
        )
        act = str(action or "").strip().upper()
        if act not in {"APPROVE_AND_EXECUTE", "APPROVE", "FOUNDER_VETO", "SOVEREIGN_VETO", "VETO"}:
            raise HTTPException(
                status_code=422,
                detail="action must be APPROVE_AND_EXECUTE or FOUNDER_VETO",
            )

        now = _utc_now()
        with self._session_factory() as db:
            petition = db.get(GovernancePetitionModel, proposal_id)
            if petition is None:
                raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")
            body = db.get(GovernanceBodyModel, petition.body_id)
            votes = (
                db.query(GovernanceVoteModel)
                .filter(GovernanceVoteModel.proposal_id == proposal_id)
                .order_by(GovernanceVoteModel.cast_at.asc())
                .all()
            )

            if act in {"FOUNDER_VETO", "SOVEREIGN_VETO", "VETO"}:
                petition.status = "VETOED_BY_FOUNDER"
                petition.settled_by = actor_id
                petition.settled_at = now
                petition.veto_reason = reason.strip() or "Absolute Founder Veto exercised by Chief Administrator."
                petition.updated_at = now
                db.commit()
                serialized = self._serialize_petition(petition, body, votes)
                audit = get_governance_audit_log().record(
                    event_type="GOVERNANCE_FOUNDER_VETO",
                    actor_id=actor_id,
                    actor_role="CHIEF_ADMINISTRATOR",
                    target_id=proposal_id,
                    action="FOUNDER_VETO",
                    outcome="VETOED_BY_FOUNDER",
                    http_status=200,
                    detail=f"Founder exercised Absolute Veto on {proposal_id}: {petition.veto_reason}",
                )
                return {**serialized, "audit_event_id": audit["event_id"]}

            # APPROVE_AND_EXECUTE
            if petition.status == "VETOED_BY_BICAMERAL_CHAMBER":
                get_governance_audit_log().record(
                    event_type="GOVERNANCE_EXECUTION_BLOCKED_BY_BICAMERAL_VETO",
                    actor_id=actor_id,
                    actor_role="CHIEF_ADMINISTRATOR",
                    target_id=proposal_id,
                    action="APPROVE_AND_EXECUTE",
                    outcome="BLOCKED_BY_BICAMERAL_CHAMBER_VETO",
                    http_status=403,
                    detail=(
                        f"Execution of {proposal_id} blocked: binding Stage 3 Bicameral Chamber Veto is in force."
                    ),
                )
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "PROPOSAL_VETOED_BY_BICAMERAL_CHAMBER: Execution is blocked by a binding "
                        "Stage 3 Bicameral Chamber Veto."
                    ),
                )
            if petition.status == "VETOED_BY_FOUNDER":
                raise HTTPException(status_code=409, detail="Proposal was already vetoed by Founder.")
            if petition.status not in {"RATIFIED_PENDING_SETTLOR", "PENDING_CHIEF_ADMIN_AUTHORIZATION"}:
                raise HTTPException(
                    status_code=400,
                    detail="Invariant Violation: Proposal lacks the mandatory quorum ratification threshold.",
                )

            petition.status = "SOVEREIGN_EXECUTED"
            petition.settled_by = actor_id
            petition.settled_at = now
            petition.updated_at = now
            db.commit()
            serialized = self._serialize_petition(petition, body, votes)

        audit = get_governance_audit_log().record(
            event_type="GOVERNANCE_SOVEREIGN_EXECUTED",
            actor_id=actor_id,
            actor_role="CHIEF_ADMINISTRATOR",
            target_id=proposal_id,
            action="APPROVE_AND_EXECUTE",
            outcome="SOVEREIGN_EXECUTED",
            http_status=200,
            detail=f"Chief Administrator authorized and executed ratified petition {proposal_id}.",
        )
        return {**serialized, "audit_event_id": audit["event_id"]}

    def reset_proposal_votes(self, proposal_id: str) -> None:
        """Reset votes on a proposal (deterministic helper for tests)."""
        self._ensure_ready()
        with self._session_factory() as db:
            db.query(GovernanceVoteModel).filter(GovernanceVoteModel.proposal_id == proposal_id).delete()
            petition = db.get(GovernancePetitionModel, proposal_id)
            if petition is not None:
                petition.status = "HOUSE_VOTE_OPEN"
                petition.settled_by = None
                petition.settled_at = None
                petition.veto_reason = None
                petition.updated_at = _utc_now()
            db.commit()

    def get_full_governance_state(self) -> Dict[str, Any]:
        """Consolidated read model for /dashboard Tab 4."""
        return {
            "mode": self.get_governance_mode(),
            "bodies": self.list_bodies(),
            "petitions": self.list_petitions(),
            "immutable_invariants": [
                {"code": code, "label": label} for code, label, _ in IMMUTABLE_CORE_INVARIANTS
            ],
            "audit_events": get_governance_audit_log().list_events(limit=30),
        }


_enclave_governance_service: Optional[EnclaveGovernanceService] = None


def get_enclave_governance_service() -> EnclaveGovernanceService:
    global _enclave_governance_service
    if _enclave_governance_service is None:
        _enclave_governance_service = EnclaveGovernanceService()
    return _enclave_governance_service
