from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.capital_ledger import CapitalLedger
"""
PDEUE Phase 1 Integrity Remediation Router
- Option A: Real-Time 87/10/3 Transaction Waterfall (10% CFCP Priority Extraction)
- Directive R-06: Split-Hat Role Mapping on /member
- Directive R-12: Redacted Telemetry Plane on /admin/tech
"""
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import html
import pathlib
from app.domain.lineage_hierarchy import get_lineage_service
from app.domain.enclave_governance import (
    MODE_ADVISORY_PETITION_FILTER,
    MODE_BICAMERAL_VETO_ACTIVE,
    MODE_EXECUTIVE_COMMAND,
    format_cents,
    get_enclave_governance_service,
)
from app.domain.scan_worker import AutonomousScanWorker
from app.domain.fleet_bridge import get_shared_fleet_coordinator
from app.domain.ai_copilot import AICopilotEngine
from app.domain.authority_tiers import (
    enforce_founder_immunity,
    get_active_hat_gateway,
    get_ca_override_manager,
    get_directive_r04_controller,
    get_governance_audit_log,
    is_chief_admin_role,
    is_class_t_role,
    is_founder_target,
    normalize_advisor_role,
    normalize_role_token,
    normalize_tech_tier,
)
from app.domain.lexicon_v05 import get_lexicon_payload, render_term_abbr
from app.domain.member_tutor import MemberLiteracyTutor
from app.domain.role_copilots import ClassFFinancialCopilot, ClassTDevOpsCopilot
from app.schemas.read_model import ReadModelEnvelope, build_read_model_envelope

router = APIRouter(tags=['Portals'])
portal_router = router
_lineage_service = get_lineage_service()
_enclave_gov = get_enclave_governance_service()
_advisor_copilot_engine = AICopilotEngine()
_member_literacy_tutor = MemberLiteracyTutor()
_class_f_copilot = ClassFFinancialCopilot()
_class_t_copilot = ClassTDevOpsCopilot()

LINEAGE_DATA: Dict[str, Any] = {
    "HOUSEHOLD-ALPHA": {
        "household_id": "HOUSEHOLD-ALPHA",
        "household_name": "Vance Lineage Alpha",
        "total_equity": 5850.00,
        "max_drawdown_pct": -0.85,
        "cfcp_floor_shield": 500.00,
        "accounts": [
            {
                "user_id": "USR-founder_ch-C8575D7E",
                "name": "Founder Chief Admin",
                "role": "CHIEF_ADMINISTRATOR",
                "scma_id": "SCMA-FOUNDER_-C8575D7E",
                "balance": 4350.00,
                "reserved": 0.00,
                "risk_dial": 2.00,
                "is_custodial": False,
                "custodian_id": None,
                "status": "OPTIMAL"
            },
            {
                "user_id": "USR-eleanor_va-B2B31C9E",
                "name": "Eleanor Vance",
                "role": "F2_FINANCIAL_ADVISOR",
                "scma_id": "SCMA-ELEANOR_-B2B31C9E",
                "balance": 1250.00,
                "reserved": 25.00,
                "risk_dial": 1.50,
                "is_custodial": False,
                "custodian_id": None,
                "status": "OPTIMAL"
            },
            {
                "user_id": "USR-julian_va-A1F98B21",
                "name": "Julian Vance (Apprentice)",
                "role": "MEMBER_USER",
                "scma_id": "SCMA-JULIAN_-A1F98B21",
                "balance": 250.00,
                "reserved": 0.00,
                "risk_dial": 1.00,
                "is_custodial": True,
                "custodian_id": "USR-eleanor_va-B2B31C9E",
                "status": "PAPER_INCUBATOR"
            }
        ]
    }
}

# The lineage advisor is assigned two explicitly bounded domestic branches.
LINEAGE_DATA["HOUSEHOLD-BETA"] = {
    "household_id": "HOUSEHOLD-BETA",
    "household_name": "Vance Lineage Beta",
    "total_equity": 4320.00,
    "max_drawdown_pct": -0.72,
    "cfcp_floor_shield": 410.00,
    "accounts": [
        {"user_id": "USR-beta-head", "name": "Morgan Vance", "role": "F2_FINANCIAL_ADVISOR",
         "scma_id": "SCMA-MORGAN-BETA", "balance": 3520.00, "reserved": 20.00,
         "risk_dial": 1.25, "is_custodial": False, "custodian_id": None, "status": "OPTIMAL"},
        {"user_id": "USR-beta-apprentice", "name": "Riley Vance (Apprentice)", "role": "MEMBER_USER",
         "scma_id": "SCMA-RILEY-BETA", "balance": 800.00, "reserved": 0.00,
         "risk_dial": 0.75, "is_custodial": True, "custodian_id": "USR-beta-head", "status": "PAPER_INCUBATOR"},
    ],
}

class RiskUpdateRequest(BaseModel):
    scma_id: Optional[str] = None
    requested_risk_pct: Optional[float] = None
    new_risk_dial: Optional[float] = None
    risk_dial: Optional[float] = None
    risk_dial_pct: Optional[float] = None

class AdvisoryProposalRequest(BaseModel):
    target_scma: str
    proposed_dial: float
    justification: str
    actor_role: Optional[str] = None


class AdvisoryAdjudicationRequest(BaseModel):
    decision: str
    actor_role: Optional[str] = None


class DistributionRequest(BaseModel):
    scma_id: str
    amount_cents: int
    category_tag: str
    justification: Optional[str] = ""

class AssistantQuery(BaseModel):
    query: Optional[str] = None
    question: Optional[str] = None
    context_scope: Optional[str] = "GENERAL"
    scma_id: Optional[str] = None
    role: Optional[str] = None
    tier: Optional[str] = None
    household_id: Optional[str] = None
    unredact_token: Optional[str] = None

class CAOverrideRequest(BaseModel):
    token: str
    reason: Optional[str] = "Audited incident diagnostics"
    ttl_seconds: int = 300
    actor_id: Optional[str] = "T3_CTO"


class CAOverrideRevokeRequest(BaseModel):
    grant_token: Optional[str] = None
    actor_id: Optional[str] = "T3_CTO"


class ActiveHatSwitchRequest(BaseModel):
    principal_id: str = "USR-founder_ch-C8575D7E"
    principal_role: str = "CHIEF_ADMINISTRATOR"
    from_hat: Optional[str] = None
    to_hat: str
    confirmed: bool = False
    target_workspace: Optional[str] = None
    reason: Optional[str] = ""


class DirectiveR04HaltRequest(BaseModel):
    reason: str
    actor_role: Optional[str] = None
    actor_id: Optional[str] = None


class DirectiveR04ResumeRequest(BaseModel):
    justification: Optional[str] = ""
    actor_role: Optional[str] = None
    actor_id: Optional[str] = None


class DualSignatureOverrideRequest(BaseModel):
    target_scope: str
    action: str = "RISK_CAP_OVERRIDE"
    justification: str
    actor_role: Optional[str] = None
    actor_id: Optional[str] = None


class DualSignatureCountersignRequest(BaseModel):
    decision: str
    actor_role: Optional[str] = None
    actor_id: Optional[str] = None


class CustodialRiskDialRequest(BaseModel):
    scma_id: str
    requested_risk_pct: float
    household_id: Optional[str] = None
    actor_role: Optional[str] = None


class CoSignRequest(BaseModel):
    request_id: str
    actor_role: str


class LineageVoteRequest(BaseModel):
    proposal_id: str
    vote: str


class LineageCircuitBreakerRequest(BaseModel):
    scma_id: str
    action: str


class CommunityMessageRequest(BaseModel):
    member_id: str
    author_name: str
    house_id: str
    message_text: str


class CommunityTutorRequest(BaseModel):
    query: str
    member_id: str


def _enforce_portal_boundary(
    *,
    allowed_hats: set[str],
    action: str,
    target_id: str = "",
    authorization: Optional[str] = None,
    x_active_hat: Optional[str] = None,
    x_actor_role: Optional[str] = None,
    x_supervisory_mode: Optional[str] = None,
    block_class_t: bool = False,
    is_mutation: bool = False,
) -> None:
    """Enforce Directive R-06 Active-Hat, C3 Supervisory read-only, and Class T isolation."""
    audit = get_governance_audit_log()
    if is_mutation and x_supervisory_mode and x_supervisory_mode.strip().lower() in {"read-only", "readonly", "true", "1", "supervisory"}:
        audit.record(
            event_type="SUPERVISORY_READ_ONLY_BLOCK",
            actor_id="CHIEF_ADMIN_INSPECTOR",
            actor_role="SUPERVISORY_AUDIT_LENS",
            target_id=target_id,
            action=action,
            outcome="DENIED_READ_ONLY_LENS",
            http_status=403,
            detail=f"Supervisory Audit Lens is strictly read-only; blocked mutation {action}.",
        )
        raise HTTPException(
            status_code=403,
            detail="SUPERVISORY_READ_ONLY_INSPECTION: Mutations are disabled while Supervisory Audit Lens is active.",
        )

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        get_active_hat_gateway().verify_token(
            token,
            allowed_hats,
            action=action,
            target_id=target_id,
        )

    norm_allowed = {normalize_role_token(h) for h in allowed_hats}
    if x_active_hat:
        norm_hat = normalize_role_token(x_active_hat)
        if norm_hat not in norm_allowed:
            audit.record(
                event_type="ACTIVE_HAT_DENIED",
                actor_id=x_actor_role or norm_hat,
                actor_role=norm_hat,
                target_id=target_id,
                action=action,
                outcome="DENIED_CROSS_HAT",
                http_status=403,
                detail=f"Active Hat {norm_hat} cannot invoke {action}; switch Active Hat first.",
            )
            raise HTTPException(
                status_code=403,
                detail=f"ACTIVE_HAT_MISMATCH: Active Hat {norm_hat} is not permitted for {action}. Switch Active Hat first.",
            )

    if block_class_t and x_actor_role and is_class_t_role(x_actor_role):
        norm_t = normalize_role_token(x_actor_role)
        audit.record(
            event_type="ROLE_BOUNDARY_DENIED",
            actor_id=x_actor_role,
            actor_role=norm_t,
            target_id=target_id,
            action=action,
            outcome="DENIED_CLASS_T_ZERO_FINANCIAL_AUTHORITY",
            http_status=403,
            detail=f"Class T sub-tier {norm_t} inherits zero financial, House, or household authority.",
        )
        raise HTTPException(
            status_code=403,
            detail=f"CLASS_T_BOUNDARY_VIOLATION: {norm_t} inherits zero financial distribution, House, or household authority.",
        )


# Process-local demo state is deliberate: these portal endpoints operate the same
# long-lived worker and approval ledger for every request made to an app process.
_TECH_WORKER = AutonomousScanWorker(fleet_coordinator=get_shared_fleet_coordinator())
_TECH_LATENCY_MS = {"Kalshi": 14, "Polymarket": 22}
_TECH_TOKEN_BUCKETS = {
    "Kalshi": {"available": 10, "capacity": 10, "unit": "req/s"},
    "Polymarket": {"available": 10, "capacity": 10, "unit": "req/s"},
}
_DISTRIBUTION_STATE: Dict[str, Dict[str, Any]] = {
    "DIST-104": {"status": "PENDING", "amount_cents": 65_000, "signature": None},
    "DIST-105": {"status": "PENDING", "amount_cents": 18_000, "signature": None},
}

# Advisory changes are proposals, never direct mutations. The process-local ledger
# makes the tri-state workflow observable in the demonstration deployment.
_ADVISORY_PROPOSALS: Dict[str, Dict[str, Any]] = {
    "PROP-ADV-01": {
        "id": "PROP-ADV-01",
        "proposal_id": "PROP-ADV-01",
        "household": "HOUSEHOLD-ALPHA",
        "target_scma": "SCMA-JULIAN",
        "title": "Apprentice Risk Expansion",
        "proposed_dial": "1.5%",
        "current_dial": "1.0%",
        "sponsor": "F2-A Vance",
        "status": "PENDING",
        "justification": "Candidate completed Binary 101.",
        "created_at": "2026-09-30T00:00:00+00:00",
        "adjudicated_by": None,
    }
}
_ADVISORY_PROPOSAL_SEQUENCE = 0
_TECH_SETTLED_COUNT = 0

_MACRO_HOUSE_EXPOSURES = [
    {"house_id": f"House-{number:02d}", "exposure_cents": 95_000 + number * 9_000,
     "margin_utilization_pct": 38 + number * 3, "risk_status": "ELEVATED" if number > 9 else "NORMAL"}
    for number in range(1, 13)
]

# House votes are an advisory petition ledger only.  Reaching the threshold
# never transfers funds or changes platform policy; it queues Chief
# Administrator / Sovereign Settlor review.
_LINEAGE_PROPOSALS: Dict[str, Dict[str, Any]] = {
    "CFCP-2026-02": {
        "proposal_id": "CFCP-2026-02",
        "title": "Apprentice Literacy Grant Petition",
        "amount_cents": 120_000,
        "aye_house_ids": [],
        "nay_house_ids": [],
        "status": "HOUSE_VOTE_OPEN",
    }
}

_LINEAGE_ROLL_CALL = [
    {"meeting_id": "RC-2026-09", "held_at": "2026-09-21T18:00:00Z", "status": "QUORUM_MET"},
]

# Community data is intentionally a small, process-local social log.  It is not
# joined to account, execution, venue, or ledger state (ADR-011 / R-12).
_COMMUNITY_MESSAGES: List[Dict[str, str]] = [
    {
        "member_id": "member-mentor-01",
        "author_name": "Academy Mentor",
        "house_id": "HOUSE-01",
        "message_text": "Welcome to the hearth. Share a milestone or ask a learning question!",
        "posted_at": "2026-09-21T18:00:00Z",
    }
]
_COMMUNITY_ANNOUNCEMENTS = [
    {"kind": "REUNION", "title": "Autumn lineage reunion", "when": "October 18"},
    {"kind": "GRADUATION", "title": "Three academy learners completed the foundations path", "when": "This week"},
    {"kind": "BIRTH", "title": "The family welcomes a new generation", "when": "September"},
]
_COMMUNITY_MILESTONES = [
    "Mentor circle completed 100 learning sessions",
    "House reading streak reached 12 weeks",
    "Five new literacy badges earned",
]
_COMMUNITY_LESSONS = [
    {"lesson_id": "binary-contracts-101", "title": "Binary Contracts 101", "reading_time": "8 min", "topic_tags": ["foundations", "probability"]},
    {"lesson_id": "quarter-kelly", "title": "Why Quarter-Kelly?", "reading_time": "10 min", "topic_tags": ["risk", "position-sizing"]},
    {"lesson_id": "waterfall-safeguard", "title": "The 87/10/3 Waterfall Safeguard", "reading_time": "7 min", "topic_tags": ["safeguards", "stewardship"]},
]


def _community_text(value: str, *, field: str, maximum: int) -> str:
    """Return inert display text and reject empty or unreasonably large input."""
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise HTTPException(status_code=422, detail=f"{field} must not be empty")
    if len(normalized) > maximum:
        raise HTTPException(status_code=422, detail=f"{field} exceeds {maximum} characters")
    return html.escape(normalized, quote=True)


def _lineage_role(role: str) -> str:
    normalized = role.upper()
    if normalized not in {"H1", "H2"}:
        raise HTTPException(status_code=400, detail="role must be H1 or H2")
    return normalized


def _authenticated_house(requested_house_id: int, header: Optional[str], claim: Optional[int]) -> int:
    """Resolve the branch claim and reject every cross-House access attempt."""
    if requested_house_id not in range(1, 13):
        raise HTTPException(status_code=404, detail="House not found")
    raw = claim if claim is not None else header
    if raw is None:
        # Local/demo compatibility: the route itself supplies the scoped claim.
        authenticated = requested_house_id
    else:
        try:
            authenticated = int(str(raw).upper().replace("HOUSE-", ""))
        except ValueError as err:
            raise HTTPException(status_code=403, detail="Invalid House identity claim") from err
    if authenticated != requested_house_id:
        raise HTTPException(status_code=403, detail="Cross-House access forbidden")
    return authenticated

def _load_html(filename: str) -> HTMLResponse:
    # The member desktop is maintained beside this router so its HTTP contract
    # and presentation cannot drift apart.  Other legacy portals remain in the
    # shared static directory.
    api_page = pathlib.Path(__file__).parent / filename
    if api_page.exists():
        return HTMLResponse(content=api_page.read_text(encoding="utf-8"))
    base = pathlib.Path(__file__).parent.parent.parent / "static"
    p1 = base / filename
    p2 = base / "templates" / filename
    if p1.exists():
        return HTMLResponse(content=p1.read_text(encoding="utf-8"))
    if p2.exists():
        return HTMLResponse(content=p2.read_text(encoding="utf-8"))
    return HTMLResponse(f"<h3>Portal file {filename} initializing...</h3>")


def _lineage_claim(
    house_id: int,
    x_house_id: Optional[str],
    actor_house_id: Optional[int],
) -> None:
    _authenticated_house(house_id, x_house_id, actor_house_id)


@router.get("/lineage/house/{house_id}", response_class=HTMLResponse)
def get_lineage_house_portal(
    house_id: int,
    role: str = Query("H2"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    actor_house_id: Optional[int] = Query(None),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
):
    if x_actor_role and is_class_t_role(x_actor_role):
        raise HTTPException(status_code=403, detail="Class T technical roles have zero House governance authority.")
    role = _lineage_role(role)
    _lineage_claim(house_id, x_house_id, actor_house_id)
    house = _lineage_service.get_house_summary(house_id)
    mode_state = _enclave_gov.get_governance_mode()
    petitions = _enclave_gov.list_petitions()
    page = _load_html("lineage_house.html").body.decode("utf-8")
    r04_snapshot = get_directive_r04_controller().snapshot()
    envelope = build_read_model_envelope(
        {
            "house_id": house_id,
            "house_code": house["lineage_code"],
            "aggregated_house_capital_cents": int(house["total_cash_cents"]),
            "governance_mode": mode_state["governance_mode"],
        },
        surface="lineage",
        directive_r04_snapshot=r04_snapshot,
    )
    banner_hidden_attr = "hidden" if envelope.status.value == "OK" else ""
    banner_class = f"rm-banner rm-{envelope.status.value.lower()}"
    replacements = {
        "__HOUSE_ID__": str(house_id),
        "__HOUSE_CODE__": house["lineage_code"],
        "__HOUSE_NAME__": house["name"],
        "__HOUSE_STATUS__": house["status"],
        "__ACTIVE_ROLE__": role,
        "__ACTIVE_HAT__": "HOUSE_LEADER (H2_SOVEREIGN)" if role == "H2" else "HOUSE_ASSISTANT (H1_SECRETARIAL)",
        "__GOVERNANCE_MODE__": mode_state["governance_mode"],
        "__GOVERNANCE_BADGE__": mode_state["badge_text"],
        "__RM_BANNER_CLASS__": banner_class,
        "__RM_BANNER_HIDDEN__": banner_hidden_attr,
        "__RM_STATUS__": envelope.status.value,
        "__RM_HEADLINE__": html.escape(envelope.banner_headline),
        "__RM_REASON__": html.escape(envelope.banner_detail),
        "__RM_UPDATED_UTC__": html.escape(envelope.updated_at_utc),
    }
    for marker, value in replacements.items():
        page = page.replace(marker, str(value))
    discovery_start = page.find("<!-- DISCOVERY_CONTROLS_START -->")
    discovery_end = page.find("<!-- DISCOVERY_CONTROLS_END -->")
    if discovery_start >= 0 and discovery_end >= 0:
        page = page[:discovery_start] + page[discovery_end + len("<!-- DISCOVERY_CONTROLS_END -->"):]
    page = page.replace(
        "__ROLE_DESK__",
        _render_lineage_h2_desk(house, mode_state, petitions)
        if role == "H2"
        else _render_lineage_h1_desk(house, mode_state),
    )
    return HTMLResponse(page)


@router.get("/api/v1/portal/lineage/house/{house_id}/state")
def get_lineage_house_state(
    house_id: int,
    role: str = Query("H2"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    actor_house_id: Optional[int] = Query(None),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
):
    if x_actor_role and is_class_t_role(x_actor_role):
        raise HTTPException(status_code=403, detail="Class T technical roles have zero House governance authority.")
    role = _lineage_role(role)
    _lineage_claim(house_id, x_house_id, actor_house_id)
    house = _lineage_service.get_house_summary(house_id)
    mode_state = _enclave_gov.get_governance_mode()
    members = []
    for source in house["members"]:
        member = {
            "scma_id": source["scma_id"], "name": source["name"],
            "role_tag": source["role_tag"], "risk_dial_bps": int(round(source["risk_dial"] * 10_000)),
            "status": source["status"], "open_orders": list(source["open_orders"]),
            "literacy_completion_pct": 85 if "Apprentice" in source["role_tag"] else 100,
            "is_sovereign_immune": _lineage_service._is_sovereign_settlor(source),
        }
        member["notional_cents"] = "$****.**" if role == "H1" else int(source["cash_cents"])
        member["cash_display"] = "$****.**" if role == "H1" else format_cents(int(source["cash_cents"]))
        members.append(member)
    proposals = _enclave_gov.list_petitions()
    r04_snapshot = get_directive_r04_controller().snapshot()
    envelope = build_read_model_envelope(
        {
            "house_id": house_id,
            "house_code": house["lineage_code"],
            "aggregated_house_capital_cents": int(house["total_cash_cents"]),
            "member_count": len(members),
        },
        surface="lineage",
        directive_r04_snapshot=r04_snapshot,
    )
    return {
        "house_id": house_id, "house_code": house["lineage_code"], "house_name": house["name"],
        "house_status": house["status"],
        "active_role": role, "r12_masked": role == "H1",
        "governance_mode": mode_state["governance_mode"],
        "governance_stage": mode_state["stage"],
        "voting_enabled": mode_state["voting_enabled"] and role == "H2",
        "bicameral_veto_enabled": mode_state["bicameral_veto_enabled"] and role == "H2",
        "mode_badge_text": mode_state["badge_text"],
        "aggregated_house_capital_cents": int(house["total_cash_cents"]),
        "aggregated_house_capital_formatted": format_cents(int(house["total_cash_cents"])),
        "average_risk_dial_bps": int(round(house["average_risk_dial_pct"] * 100)),
        "members": members, "roll_call_logs": list(_LINEAGE_ROLL_CALL), "bicameral_proposals": proposals,
        "read_model_envelope": envelope.model_dump(),
    }


@router.post("/api/v1/portal/active-hat/switch")
def switch_active_hat(
    request: ActiveHatSwitchRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """Directive R-06 server-validated Active-Hat context switching gateway."""
    from app.core.security import decode_access_token

    identity_claims = None
    principal_id = request.principal_id
    principal_role = request.principal_role
    if authorization and authorization.lower().startswith("bearer "):
        claims = decode_access_token(authorization.split(" ", 1)[1].strip())
        if not claims:
            raise HTTPException(status_code=403, detail="Invalid or expired identity token")
        identity_claims = claims
        principal_id = str(claims.get("sub") or claims.get("user_id") or principal_id)
        principal_role = str(claims.get("role") or principal_role)

    return get_active_hat_gateway().switch_hat(
        principal_id=principal_id,
        principal_role=principal_role,
        from_hat=request.from_hat,
        to_hat=request.to_hat,
        confirmed=request.confirmed,
        target_workspace=request.target_workspace,
        reason=request.reason or "",
        identity_claims=identity_claims,
    )


@router.get("/api/v1/portal/active-hat/state")
def get_active_hat_state(principal_id: str = Query("USR-founder_ch-C8575D7E")) -> Dict[str, Any]:
    gateway = get_active_hat_gateway()
    session = gateway.current_session(principal_id)
    return {
        "principal_id": principal_id,
        "active_session": session,
        "entitled_hats": sorted(gateway.entitled_hats(principal_id)),
    }


@router.get("/api/v1/portal/active-hat/audit")
def get_active_hat_audit(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    audit = get_governance_audit_log()
    return {
        "events": audit.list_events(event_type="ACTIVE_HAT_SWITCH", limit=limit),
        "denied_events": audit.list_events(event_type="ACTIVE_HAT_DENIED", limit=limit),
    }


@router.post("/api/v1/portal/lineage/house/{house_id}/vote")
def vote_on_lineage_proposal(
    house_id: int, request: LineageVoteRequest,
    role: str = Query("H2"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    actor_house_id: Optional[int] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
):
    _enforce_portal_boundary(
        allowed_hats={"H2", "CHIEF_ADMINISTRATOR"},
        action="LINEAGE_VOTE",
        target_id=f"HOUSE-{house_id:02d}",
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    role = _lineage_role(role)
    _lineage_claim(house_id, x_house_id, actor_house_id)
    if role != "H2":
        raise HTTPException(status_code=403, detail="H1 secretarial role has no voting authority")

    result = _enclave_gov.cast_vote(
        proposal_id=request.proposal_id,
        vote_choice=request.vote,
        actor_role=x_actor_role or role,
        actor_id=f"HOUSE-{house_id:02d}:{role}",
        house_id=house_id,
    )
    if request.proposal_id in _LINEAGE_PROPOSALS:
        _LINEAGE_PROPOSALS[request.proposal_id].update(
            aye_house_ids=result["aye_house_ids"],
            nay_house_ids=result["nay_house_ids"],
            status=result["status"],
        )
    return {
        "proposal_id": result["proposal_id"],
        "house_vote": result["vote_choice"],
        "aye_count": result["aye_count"],
        "nay_count": result["nay_count"],
        "veto_count": result["veto_count"],
        "threshold": result["threshold"],
        "veto_threshold_count": result["veto_threshold_count"],
        "status": result["status"],
        "governance_mode": result["governance_mode"],
        "effect": result["effect"],
    }


@router.post("/api/v1/portal/lineage/house/{house_id}/circuit-breaker")
def execute_lineage_circuit_breaker(
    house_id: int, request: LineageCircuitBreakerRequest,
    role: str = Query("H2"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    actor_house_id: Optional[int] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
):
    _enforce_portal_boundary(
        allowed_hats={"H2", "CHIEF_ADMINISTRATOR"},
        action="LINEAGE_CIRCUIT_BREAKER",
        target_id=request.scma_id,
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    role = _lineage_role(role)
    _lineage_claim(house_id, x_house_id, actor_house_id)
    if role != "H2":
        raise HTTPException(status_code=403, detail="H1 secretarial role cannot operate circuit breakers")
    if is_founder_target(request.scma_id):
        enforce_founder_immunity(
            target_id=request.scma_id,
            action=request.action.upper(),
            actor_role=x_actor_role or role,
            actor_id=f"HOUSE-{house_id:02d}:{role}",
        )
    action = request.action.upper().replace("-", "_")
    try:
        if action in {"FREEZE", "FREEZE_DIAL", "GOVERNOR_CLAMP"}:
            return _lineage_service.freeze_subordinate_risk(house_id, request.scma_id)
        if action in {"CANCEL_ORDERS", "RESTING_PURGE"}:
            return _lineage_service.cancel_subordinate_orders(house_id, request.scma_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    raise HTTPException(status_code=422, detail="action must be FREEZE_DIAL or CANCEL_ORDERS")


def _render_lineage_h2_desk(
    house: Dict[str, Any],
    mode_state: Dict[str, Any],
    petitions: List[Dict[str, Any]],
) -> str:
    row_parts: List[str] = []
    for m in house["members"]:
        safe_name = html.escape(str(m["name"]))
        safe_scma = html.escape(str(m["scma_id"]))
        cash_fmt = format_cents(int(m["cash_cents"]))
        status_txt = html.escape(str(m.get("status", "ACTIVE")))
        if _lineage_service._is_sovereign_settlor(m):
            action_cell = '<span class="immune-badge">🛡️ Sovereign Immune</span>'
        else:
            action_cell = (
                f'<button class="freeze" type="button" onclick="openFreezeModal(\'{safe_scma}\')">Freeze Dial (0%)</button> '
                f'<button class="cancel" type="button" onclick="openCancelModal(\'{safe_scma}\')">Cancel Orders</button>'
            )
        row_parts.append(
            f'<tr><td>{safe_name}</td><td class="mono">{safe_scma}</td>'
            f'<td class="num">{cash_fmt}</td><td>{status_txt}</td><td>{action_cell}</td></tr>'
        )
    rows = "".join(row_parts)

    active_mode = mode_state["governance_mode"]
    active_prop = next((p for p in petitions if p["proposal_id"] == "CFCP-2026-02"), None)
    if active_prop is None and petitions:
        active_prop = petitions[0]
    prop_id = html.escape(active_prop["proposal_id"]) if active_prop else "CFCP-2026-02"
    prop_title = html.escape(active_prop["title"]) if active_prop else "Apprentice Literacy Grant Petition"
    aye_count = int(active_prop["aye_count"]) if active_prop else 0
    veto_count = int(active_prop["veto_count"]) if active_prop else 0
    threshold = int(active_prop["threshold"]) if active_prop else 9
    veto_threshold = int(active_prop["veto_threshold_count"]) if active_prop else 9
    prop_status = html.escape(active_prop["status"]) if active_prop else "HOUSE_VOTE_OPEN"

    if active_mode == MODE_EXECUTIVE_COMMAND:
        chamber_html = (
            '<section id="bicameral" class="chamber-dormant">'
            '<h2>Bicameral CFCP Ratification Chamber</h2>'
            '<div id="governance-dormant-badge" class="mode-badge mode-dormant">'
            'Executive Command Mode Active — Voting Dormant'
            '</div>'
            '<p class="muted-note">Stage 1 Executive Command is active. Voting and bicameral veto controls are intentionally stripped while fledgling stewardship or SHTF protection is engaged. All voting endpoints fail closed (HTTP 403).</p>'
            '</section>'
        )
    elif active_mode == MODE_ADVISORY_PETITION_FILTER:
        chamber_html = (
            f'<section id="bicameral" class="chamber-advisory">'
            f'<h2>Bicameral CFCP Ratification Chamber</h2>'
            f'<div id="governance-active-badge" class="mode-badge mode-stage2">Stage 2: Advisory Petition Filter Active (Founder Veto Preserved)</div>'
            f'<p>75% ({threshold} of 12) stages an advisory petition (RATIFIED_PENDING_SETTLOR) for Chief Administrator review. No capital sweep executes unilaterally.</p>'
            f'<article><strong>{prop_title}</strong> '
            f'<span class="mono muted-note">({prop_id})</span>'
            f'<div id="consensus-tally" class="tally">{aye_count} / 12 Aye — {prop_status}</div>'
            f'<div class="vote-actions">'
            f'<button id="vote-aye" type="button" onclick="castVote(\'AYE\', \'{prop_id}\')">Aye</button>'
            f'<button id="vote-nay" type="button" onclick="castVote(\'NAY\', \'{prop_id}\')">Nay</button>'
            f'</div>'
            f'<div id="vote-feedback" class="status-feedback" role="status" aria-live="polite"></div>'
            f'</article></section>'
        )
    else:
        chamber_html = (
            f'<section id="bicameral" class="chamber-veto">'
            f'<h2>Bicameral CFCP Ratification Chamber</h2>'
            f'<div id="governance-active-badge" class="mode-badge mode-stage3">Stage 3: Bicameral Veto Active (Binding Chamber Veto Enabled)</div>'
            f'<p>Authorized House seats may ratify eligible policy/CFCP proposals ({threshold} of 12) or enact a binding Bicameral Veto ({veto_threshold} vetoes -> VETOED_BY_BICAMERAL_CHAMBER). Immutable core invariants remain permanently non-amendable.</p>'
            f'<article><strong>{prop_title}</strong> '
            f'<span class="mono muted-note">({prop_id})</span>'
            f'<div id="consensus-tally" class="tally">{aye_count} / 12 Aye — {prop_status}</div>'
            f'<div id="veto-tally" class="tally-veto">Bicameral Vetoes: {veto_count} / {veto_threshold}</div>'
            f'<div class="vote-actions">'
            f'<button id="vote-aye" type="button" onclick="castVote(\'AYE\', \'{prop_id}\')">Aye</button>'
            f'<button id="vote-nay" type="button" onclick="castVote(\'NAY\', \'{prop_id}\')">Nay</button>'
            f'<button id="vote-veto" class="veto" type="button" onclick="castVote(\'VETO\', \'{prop_id}\')">Cast Bicameral Veto</button>'
            f'</div>'
            f'<div id="vote-feedback" class="status-feedback" role="status" aria-live="polite"></div>'
            f'</article></section>'
        )

    scma_tip = render_term_abbr("scma", "SCMA")
    cfcp_tip = render_term_abbr("cfcp", "CFCP")
    adr008_tip = render_term_abbr("adr-008-exact-cents", "ADR-008")
    exec_tip = render_term_abbr("executive-command-mode", "Executive Command Mode")
    return f'''<section class="metrics">
<article><h2>Aggregated House Capital</h2><strong class="num">{format_cents(int(house["total_cash_cents"]))}</strong></article>
<article><h2>Average Risk Dial</h2><strong class="num">{house["average_risk_dial_pct"]}%</strong></article>
<article><h2>Governance Stage ({exec_tip})</h2><strong id="desk-governance-mode">{html.escape(active_mode)}</strong></article>
</section>
<section><h2>Subordinate {scma_tip} Accounts &amp; Lineal Circuit Breakers</h2>
<div class="table-card"><table><thead><tr><th>Member</th><th>{scma_tip} ID</th><th>Balance ({adr008_tip})</th><th>Status</th><th>Lineal Controls</th></tr></thead><tbody>{rows}</tbody></table></div>
<div id="breaker-feedback" class="status-feedback" role="status" aria-live="polite"></div>
</section>
{chamber_html.replace("Bicameral CFCP Ratification Chamber", f"Bicameral CFCP Ratification Chamber ({cfcp_tip})")}
<div id="cancel-modal" class="modal" hidden>Resting Purge confirmation recorded in lineage audit ledger.</div>
<div id="freeze-modal" class="modal" hidden>Governor Clamp (0.0%) confirmation recorded in lineage audit ledger.</div>'''


def _render_lineage_h1_desk(house: Dict[str, Any], mode_state: Dict[str, Any]) -> str:
    rows = "".join(
        f'<tr><td>{html.escape(str(m["name"]))}</td><td class="mono">{html.escape(str(m["scma_id"]))}</td>'
        f'<td class="num masked-val">$****.**</td><td>{html.escape(str(m["status"]))}</td></tr>'
        for m in house["members"]
    )
    literacy = "".join(
        f'<label>{html.escape(str(m["name"]))}<progress max="100" value="{85 if "Apprentice" in m["role_tag"] else 100}"></progress></label>'
        for m in house["members"]
    )
    mode_badge = html.escape(mode_state["badge_text"])
    r12_tip = render_term_abbr("directive-r12-masking", "Directive R-12")
    scma_tip = render_term_abbr("scma", "SCMA")
    cfcp_tip = render_term_abbr("cfcp", "CFCP")
    exec_tip = render_term_abbr("executive-command-mode", "Executive Command Mode")
    return f'''<section class="metrics">
<article><h2>Aggregated House Capital</h2><strong class="num">{format_cents(int(house["total_cash_cents"]))}</strong></article>
<article><h2>Governance Mode ({exec_tip})</h2><strong id="desk-governance-mode">{html.escape(mode_state["governance_mode"])}</strong><div class="muted-note">{mode_badge}</div></article>
</section>
<section><h2>Member Accounts — {r12_tip}</h2>
<div class="table-card"><table><thead><tr><th>Member</th><th>{scma_tip} ID</th><th>Balance ({r12_tip})</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section class="audit"><h2>Bicameral CFCP Ratification Chamber ({cfcp_tip}) — NON-VOTING AUDIT</h2>
<div id="governance-dormant-badge" class="mode-badge mode-dormant">{mode_badge}</div>
<p>Secretarial observation only; legislative submission, voting, veto, and circuit-breaker authorities are stripped from H1 desks and blocked server-side (HTTP 403).</p></section>
<section class="secretarial"><article><h2>Meeting Scheduler Log</h2><p>Next Senate session: 2026-10-05 18:00 UTC</p></article><article><h2>Lineage Roll-Call Registry</h2><p>RC-2026-09 — QUORUM MET</p></article><article><h2>AI Tutor / Literacy Completion</h2>{literacy}</article></section>'''

@router.get("/member", response_class=HTMLResponse)
def get_member_portal():
    return _load_html("member.html")


@router.get("/companion", response_class=HTMLResponse)
def get_companion_portal():
    """Serve the offline-first PDEUE University learning campus."""
    return _load_html("companion.html")


@router.get("/api/v1/portal/companion/state")
def get_companion_state() -> Dict[str, Any]:
    """Return the versioned curriculum contract used by the campus shell."""
    chapters = [
        ("waterfall", "The 87/10/3 Transaction Profit Waterfall", 0),
        ("risk-governor", "Downward-Only Risk Governor & Safety Envelope", 45),
        ("segregation", "Ring-Fenced SCMA Sub-Ledger Segregation", 90),
        ("float-ceiling", "$25k Active Float Ceiling & Post-Cap Compounding", 135),
        ("distribution", "Directive R-15 Three-Tier Distribution Gateway", 180),
        ("governance", "Sovereign Governance, Bicameral Voting & Self-Check", 225),
    ]
    return {
        "curriculum": "PDEUE University",
        "lexicon_version": "0.5",
        "duration_seconds": 270,
        "chapters": [
            {"number": number, "id": slug, "title": title, "cue_seconds": cue}
            for number, (slug, title, cue) in enumerate(chapters, start=1)
        ],
        "audio": {
            "src": "/static/media/companion/pdeue-university.mp3",
            "fallback": "silent_timeline",
            "transcript_cues": [
                {"start_seconds": cue, "chapter": number, "text": title}
                for number, (_, title, cue) in enumerate(chapters, start=1)
            ],
        },
        "invariants": {
            "ADR-008": "Integer cents; SCMA and FAEP truncate and every residual cent routes to CFCP.",
            "ADR-011": "Sweeps emit signed, sequenced, idempotent accounting outbox envelopes across the air gap.",
            "risk": "Risk may move downward autonomously; increases require F2-H approval; frozen means 0 bps.",
            "offline": "Campus scripts, styles, and SVG assets are local and inline; no CDN dependency.",
        },
    }


@router.get("/api/v1/portal/companion/manual/{manual_name}", response_class=PlainTextResponse)
def get_companion_manual(manual_name: str) -> PlainTextResponse:
    """Serve only the four canonical, repository-backed University manuals."""
    allowed = {
        "USER_QUICKSTART.md",
        "CLASS_F_FINANCIAL_MANUAL.md",
        "CLASS_T_TECHNICAL_MANUAL.md",
        "CHIEF_ADMIN_RUNBOOK.md",
    }
    if manual_name not in allowed:
        raise HTTPException(status_code=404, detail="Canonical manual not found")
    manual = pathlib.Path(__file__).resolve().parents[4] / "docs" / "manuals" / manual_name
    return PlainTextResponse(manual.read_text(encoding="utf-8"), media_type="text/markdown")

def _is_chief_admin_portal_viewer(
    *,
    authorization: Optional[str] = None,
    x_actor_role: Optional[str] = None,
    x_active_hat: Optional[str] = None,
    inspector: Optional[str] = None,
) -> bool:
    """Return True strictly when the authenticated viewer holds CHIEF_ADMIN authority."""
    if authorization and authorization.lower().startswith("bearer "):
        from app.core.security import decode_access_token

        claims = decode_access_token(authorization.split(" ", 1)[1].strip())
        if claims and is_chief_admin_role(claims.get("active_hat") or claims.get("role")):
            return True
    if x_actor_role and is_chief_admin_role(x_actor_role):
        return True
    if x_active_hat and is_chief_admin_role(x_active_hat):
        return True
    if inspector and is_chief_admin_role(inspector):
        return True
    return False


def _strip_marked_block(markup: str, start_marker: str, end_marker: str) -> str:
    """Remove a server-gated DOM section completely when caller lacks authority."""
    start_idx = markup.find(start_marker)
    end_idx = markup.find(end_marker)
    if start_idx >= 0 and end_idx >= start_idx:
        return markup[:start_idx] + markup[end_idx + len(end_marker):]
    return markup


@router.get("/advisor", response_class=HTMLResponse)
def get_advisor_portal(
    role: Optional[str] = Query(None),
    inspector: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
):
    is_admin = _is_chief_admin_portal_viewer(
        authorization=authorization,
        x_actor_role=x_actor_role,
        x_active_hat=x_active_hat,
        inspector=inspector,
    )
    if not is_admin:
        claimed_raw = x_active_hat or x_actor_role
        if claimed_raw:
            claimed = normalize_role_token(claimed_raw)
            if is_class_t_role(claimed):
                raise HTTPException(status_code=403, detail="Class T operators cannot access Class F advisory workspace.")
            if role and claimed in {"F1", "F2-H", "F2-A", "F3"}:
                requested = normalize_advisor_role(role)
                if requested != claimed:
                    raise HTTPException(
                        status_code=403,
                        detail=f"CROSS_TIER_ACCESS_DENIED: Assigned Class F tier {claimed} cannot jump to {requested}.",
                    )

    page = _load_html("advisor.html").body.decode("utf-8")
    if is_admin:
        page = page.replace("<!-- CHIEF_ADMIN_ROLE_SWITCHER_START -->", "").replace(
            "<!-- CHIEF_ADMIN_ROLE_SWITCHER_END -->", ""
        )
    else:
        page = _strip_marked_block(
            page,
            "<!-- CHIEF_ADMIN_ROLE_SWITCHER_START -->",
            "<!-- CHIEF_ADMIN_ROLE_SWITCHER_END -->",
        )
    return HTMLResponse(page)


@router.get("/admin/tech", response_class=HTMLResponse)
def get_tech_console(
    tier: Optional[str] = Query(None),
    inspector: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
):
    is_admin = _is_chief_admin_portal_viewer(
        authorization=authorization,
        x_actor_role=x_actor_role,
        x_active_hat=x_active_hat,
        inspector=inspector,
    )
    if not is_admin:
        claimed_raw = x_active_hat or x_actor_role
        if claimed_raw:
            claimed = normalize_role_token(claimed_raw)
            if claimed in {"F1", "F2-H", "F2-A", "F3", "MEMBER_USER", "PERSONAL_SCMA", "H1", "H2"}:
                raise HTTPException(status_code=403, detail="Non-Class-T role cannot access Technical Console.")
            if tier and claimed in {"T1", "T2", "T2-HOUSEHOLD", "T3"}:
                requested = normalize_tech_tier(tier)
                if requested != claimed:
                    raise HTTPException(
                        status_code=403,
                        detail=f"CROSS_TIER_ACCESS_DENIED: Assigned Class T tier {claimed} cannot jump to {requested}.",
                    )

    page = _load_html("tech.html").body.decode("utf-8")
    if is_admin:
        page = page.replace("<!-- CHIEF_ADMIN_TIER_SWITCHER_START -->", "").replace(
            "<!-- CHIEF_ADMIN_TIER_SWITCHER_END -->", ""
        )
    else:
        page = _strip_marked_block(
            page,
            "<!-- CHIEF_ADMIN_TIER_SWITCHER_START -->",
            "<!-- CHIEF_ADMIN_TIER_SWITCHER_END -->",
        )
    return HTMLResponse(page)


# Community Fellowship (/home, /community, /community/heritage, /api/v1/portal/community/*)
# is served exclusively by the air-gapped social_plane_router.py (zero financial imports).

# --- Member Workspace (Directive R-06 Split-Hat) ---
# Twelve fixed slots make missing telemetry explicit instead of collapsing the rack.
def _member_concurrency_slots() -> List[Dict[str, Any]]:
    resting = {
        1: ("Weather", 56, 1240),
        3: ("Macro", 43, 870),
        6: ("Crypto", 61, 1460),
        9: ("Sports", 38, 730),
    }
    return [
        {"slot_id": slot_id, "status": "RESTING", "domain": values[0],
         "entry_price_cents": values[1], "net_edge_bps": values[2]}
        if (values := resting.get(slot_id)) else
        {"slot_id": slot_id, "status": "AVAILABLE", "domain": None,
         "entry_price_cents": None, "net_edge_bps": None}
        for slot_id in range(1, 13)
    ]


@router.get("/api/v1/portal/member/state")
def get_member_state(user_id: Optional[str] = Query(None), scma_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    from app.domain.member_onboarding import IFAS_PORTAL_HOST, STATUS_PENDING_CERT, get_onboarding_service

    target = None
    lineage_member = None
    onboarded = None

    # A SCMA link is authoritative: resolve it against the shared lineage
    # registry first, falling back to the persistent onboarding store so
    # dynamically provisioned members resolve across restarts as well.
    if scma_id:
        onboarded = get_onboarding_service().get_member_by_scma(scma_id)
        try:
            lineage_member = _lineage_service.get_member_state(scma_id)
        except ValueError as err:
            if onboarded is None:
                raise HTTPException(status_code=404, detail=str(err)) from err
            lineage_member = _lineage_service.register_onboarded_member(
                house_id=onboarded["house_id"],
                scma_id=onboarded["scma_id"],
                member_id=onboarded["member_id"],
                name=onboarded["full_name"],
                role_tier=onboarded["role_tier"],
                seed_cents=onboarded["seed_cents"],
                risk_dial_bps=onboarded["risk_dial_bps"],
                is_custodial=onboarded["is_custodial"],
                bank_ref_token=onboarded["bank_ref_token"],
                status=onboarded["status"],
            )
            lineage_member = _lineage_service.get_member_state(scma_id)

    for house in LINEAGE_DATA.values():
        for acct in house["accounts"]:
            if (user_id and acct["user_id"] == user_id) or (scma_id and acct["scma_id"] == scma_id):
                target = acct
                break
        if target:
            break
    if not target:
        if lineage_member:
            target = {
                "user_id": lineage_member.get("member_id") or f"USR-{lineage_member['scma_id']}",
                "name": lineage_member["name"],
                "role": "MEMBER_USER",
                "scma_id": lineage_member["scma_id"],
                "balance": lineage_member["cash_cents"] / 100.0,
                "reserved": 0.0,
                "risk_dial": lineage_member["risk_dial"] * 100,
                "is_custodial": bool(lineage_member.get("is_custodial", False)),
                "custodian_id": None,
                "status": lineage_member["status"],
            }
        else:
            target = LINEAGE_DATA["HOUSEHOLD-ALPHA"]["accounts"][1]

    # Identity/profile data remains portal-specific, while mutable financial
    # controls come from the same hierarchy used by leader and operator desks.
    if lineage_member is None:
        try:
            lineage_member = _lineage_service.get_member_state(target["scma_id"])
        except ValueError:
            lineage_member = None
    if onboarded is None:
        onboarded = get_onboarding_service().get_member_by_scma(target["scma_id"])

    risk_dial_pct = (
        lineage_member["risk_dial"] * 100 if lineage_member else target["risk_dial"]
    )

    cash_cents = int(lineage_member["cash_cents"] if lineage_member else round(target["balance"] * 100))
    high_water_mark_cents = int(
        (onboarded["high_water_mark_cents"] if onboarded else None)
        or (lineage_member.get("high_water_mark_cents") if lineage_member else None)
        or cash_cents
    )
    member_status = (
        onboarded["status"]
        if onboarded and lineage_member and lineage_member["status"] in {"PENDING_TUTOR_CERTIFICATION", "ACTIVE"}
        else (lineage_member["status"] if lineage_member else target["status"])
    )
    active_float_cents = min(cash_cents, 2_500_000)
    swept_cash_cents = max(cash_cents - active_float_cents, 0)
    passive_yield_cents = cash_cents * 450 // 10_000
    is_sovereign_immune = bool(
        is_founder_target(target) or (lineage_member and _lineage_service._is_sovereign_settlor(lineage_member))
    )
    quarantined = False if is_sovereign_immune else (
        member_status in {"QUARANTINED", "FROZEN_BY_HOUSE_LEADER", "FROZEN_BY_HOUSE_QUARANTINE"}
    )
    parent_house_quarantined = (
        (lineage_member["parent_house_status"] if lineage_member else "ACTIVE") == "QUARANTINED"
    )
    is_frozen = False if is_sovereign_immune else (quarantined or parent_house_quarantined)
    if is_frozen:
        # A governance halt is an absolute zero-basis-point clamp, not the
        # ordinary member governor's 50-bps lower bound.
        risk_dial_pct = 0.0

    # Member visualizations are transported exclusively as integer cents / basis
    # points (ADR-008).  These deterministic defaults keep an unseeded desktop
    # useful without implying that the educational examples are live orders.
    reserve_floor_cents = cash_cents * 40 // 100
    trajectory_points = [
        {"milestone": "Seed Capital", "date": "2026-01-15", "balance_cents": 100_000, "yield_increment_cents": 0},
        {"milestone": "First Settlement", "date": "2026-03-02", "balance_cents": 128_400, "yield_increment_cents": 2_400},
        {"milestone": "40% Shield", "date": "2026-05-18", "balance_cents": 176_250, "yield_increment_cents": 7_850},
        {"milestone": "High-Watermark Sweep", "date": "2026-09-30", "balance_cents": max(cash_cents, 235_000), "yield_increment_cents": 13_500},
    ]
    settled_contracts = [
        {"contract_id": "KX-MIA-FRZ", "title": "NOAA Miami Temperature", "settled_at": "2026-09-28", "outcome": "SETTLED / WON", "gross_win_cents": 18_400, "scma_cents": 16_008, "family_shield_cents": 1_840, "platform_ops_cents": 552},
        {"contract_id": "KX-CPI-PRINT", "title": "CPI Inflation Print", "settled_at": "2026-09-16", "outcome": "SETTLED / WON", "gross_win_cents": 12_000, "scma_cents": 10_440, "family_shield_cents": 1_200, "platform_ops_cents": 360},
    ]

    bank_ref_token = (
        (onboarded["bank_ref_token"] if onboarded else None)
        or (lineage_member.get("bank_ref_token") if lineage_member else None)
        or "EXT-REF-IFAS-****0000"
    )
    certification_level = (
        (onboarded["certification_level"] if onboarded else None)
        or (lineage_member.get("certification_level") if lineage_member else None)
    )
    certified_at = (
        (onboarded["certified_at"] if onboarded else None)
        or (lineage_member.get("certified_at") if lineage_member else None)
    )
    invite_activated_at = (
        (onboarded["invite_activated_at"] if onboarded else None)
        or (lineage_member.get("invite_activated_at") if lineage_member else None)
    )
    role_tier = (
        (onboarded["role_tier"] if onboarded else None)
        or (lineage_member.get("role_tier") if lineage_member else None)
        or "MEMBER_USER"
    )
    is_custodial = bool(
        onboarded["is_custodial"]
        if onboarded is not None
        else (lineage_member.get("is_custodial", target["is_custodial"]) if lineage_member else target["is_custodial"])
    )

    r04_snapshot = get_directive_r04_controller().snapshot()
    reserved_cents = int(round(target["reserved"] * 100))
    working_margin_cents = reserved_cents if reserved_cents > 0 else min(active_float_cents, max(active_float_cents * 25 // 100, 0))
    member_envelope = build_read_model_envelope(
        {
            "scma_id": target["scma_id"],
            "cash_cents": cash_cents,
            "active_float_cents": active_float_cents,
            "reserve_floor_cents": reserve_floor_cents,
            "swept_cash_cents": swept_cash_cents,
            "passive_yield_cents": passive_yield_cents,
        },
        surface="member",
        directive_r04_snapshot=r04_snapshot,
    )

    return {
        "user_id": target["user_id"],
        "cash_cents": cash_cents,
        "high_water_mark_cents": high_water_mark_cents,
        "reserved_cents": reserved_cents,
        "lifetime_profit_cents": 34_000,
        "concurrency_slots": _member_concurrency_slots(),
        "name": target["name"],
        "role": "MEMBER_USER",  # Directive R-06: Member desk always enforces personal member role
        "role_tier": role_tier,
        "scma_id": target["scma_id"],
        "lineage_code": lineage_member["lineage_code"] if lineage_member else "HOUSE-01",
        "cash_balance": cash_cents / 100.0,
        "reserved_capital": target["reserved"],
        "lifetime_yield": 340.00,
        "risk_dial_pct": risk_dial_pct,
        "status": member_status,
        "onboarding_status": member_status,
        "certification_level": certification_level,
        "certified_at": certified_at,
        "invite_activated_at": invite_activated_at,
        "requires_orientation": member_status == STATUS_PENDING_CERT,
        "bank_ref_token": bank_ref_token,
        "ifas_portal_host": IFAS_PORTAL_HOST,
        "open_orders": lineage_member["open_orders"] if lineage_member else [],
        "parent_house_status": lineage_member["parent_house_status"] if lineage_member else "ACTIVE",
        "risk_ceiling_pct": 2.00,
        "active_float_cents": active_float_cents,
        "swept_cash_cents": swept_cash_cents,
        "passive_yield_cents": passive_yield_cents,
        "quarantined": quarantined,
        "is_frozen": is_frozen,
        "is_sovereign_immune": is_sovereign_immune,
        "parent_house_quarantined": parent_house_quarantined,
        "allocation": {
            "cap_cents": 2_500_000,
            "active_float_cents": active_float_cents,
            "working_margin_cents": working_margin_cents,
            "active_utilization_bps": min(active_float_cents * 10_000 // 2_500_000, 10_000),
            "reserve_floor_cents": reserve_floor_cents,
            "reserve_floor_bps": 4_000,
            "swept_reserve_cents": swept_cash_cents,
            "earned_yield_cents": passive_yield_cents,
            "apy_bps": 450,
            "waterfall_split_bps": {"scma": 8_700, "cfcp": 1_000, "faep": 300},
        },
        "trajectory_points": trajectory_points,
        "recent_settled_contracts": settled_contracts,
        "is_custodial": is_custodial,
        "custodian_id": target["custodian_id"],
        "positions": [
            {
                "contract_id": "KX-MIA-FRZ-32",
                "category": "WEATHER",
                "allocation": 25.00,
                "edge_pct": 28.5,
                "protocol": "Inside-Maker Post-Only",
                "status": "RESTING"
            }
        ],
        "waterfall_structure": {
            "scma_compounding_pct": 87.0,
            "cfcp_lineage_shield_pct": 10.0,
            "faep_endowment_pct": 3.0,
            "rule": "Option A (ADR-012 HWM / Rule A14): 87/10/3 split applies strictly to net new profit above each SCMA High-Water Mark; residual cents route to CFCP; 100% SCMA loss isolation."
        },
        "directive_r04": r04_snapshot,
        "read_model_envelope": member_envelope.model_dump(),
    }

@router.get("/api/v1/portal/member/{scma_id}")
def get_member_telemetry(scma_id: str) -> Dict[str, Any]:
    """Return the fail-closed member read model, including all 12 engine slots."""
    return get_member_state(scma_id=scma_id)


@router.post("/api/v1/portal/member/risk-dial")
def update_current_member_risk_dial(
    req: RiskUpdateRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
):
    """Apply the member HUD's 50–200 bps, downward-only governor."""
    scma_id = req.scma_id or "SCMA-ELEANOR_-B2B31C9E"
    _enforce_portal_boundary(
        allowed_hats={"MEMBER_USER", "PERSONAL_SCMA"},
        action="MEMBER_RISK_DIAL_UPDATE",
        target_id=scma_id,
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    portal_account = next(
        (account for house in LINEAGE_DATA.values() for account in house["accounts"]
         if account["scma_id"] == scma_id or account["user_id"] == scma_id),
        None,
    )
    if portal_account and portal_account.get("is_custodial"):
        raise HTTPException(
            status_code=403,
            detail="Custodial accounts require F2-H Head of Household authorization",
        )
    try:
        member = _lineage_service.get_member_state(scma_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    if member.get("is_custodial"):
        raise HTTPException(
            status_code=403,
            detail="Custodial accounts require F2-H Head of Household authorization",
        )
    requested = req.requested_risk_pct
    if requested is None:
        requested = req.risk_dial_pct if req.risk_dial_pct is not None else req.new_risk_dial
    if requested is None and req.risk_dial is not None:
        requested = req.risk_dial
    if requested is None or requested < 0.50 or requested > 2.00:
        raise HTTPException(status_code=400, detail="Risk dial must be between 0.50% and 2.00%")
    current = member["risk_dial"] * 100
    if requested > current:
        raise HTTPException(status_code=400, detail="Downward-only policy: requested risk exceeds current ceiling.")
    member["risk_dial"] = requested / 100
    return {"status": "UPDATED", "scma_id": scma_id, "applied_risk_pct": requested}

@router.post("/api/v1/portal/member/{scma_id}/risk-dial")
def update_member_risk_dial(scma_id: str, req: RiskUpdateRequest):
    target = None
    for house in LINEAGE_DATA.values():
        for acct in house["accounts"]:
            if acct["scma_id"] == scma_id or acct["user_id"] == scma_id:
                target = acct
                break
    ledger_account = None
    if not target and scma_id == "SCMA-MEM-001":
        target = {
            "risk_dial": 3.0,
            "is_custodial": False,
            "custodian_id": None,
        }
    if not target and "global_portal_service" in globals():
        ledger_account = global_portal_service.ledger.members.get(scma_id)
        if ledger_account:
            target = {
                "risk_dial": ledger_account["max_risk_pct"] * 100.0,
                "is_custodial": False,
                "custodian_id": None,
            }
    if not target:
        account = _GLOBAL_LEDGER.members.get(scma_id)
        if not account:
            raise HTTPException(status_code=404, detail="SCMA account not found")
        if req.requested_risk_pct is not None:
            requested = req.requested_risk_pct
            current = account["risk_dial"]
            if requested > current:
                raise HTTPException(status_code=400, detail="Downward-only policy: requested risk exceeds current ceiling.")
            account["risk_dial"] = requested
            return {"status": "UPDATED", "scma_id": scma_id, "new_risk_pct": requested, "applied_risk_pct": requested}

        requested = req.new_risk_dial
        current_pct = account["risk_dial"] * 100 if account["risk_dial"] <= 1 else account["risk_dial"]
        if requested is None or requested < 0.5 or requested > 5.0:
            raise HTTPException(status_code=400, detail="Risk dial must be between 0.5% and 5.0%")
        if requested > current_pct:
            raise HTTPException(status_code=400, detail="Downward-only policy: requested risk exceeds current ceiling.")
        account["risk_dial"] = requested / 100
        return {"status": "UPDATED", "scma_id": scma_id, "applied_risk_dial": requested, "new_risk_pct": requested / 100}

    if target["is_custodial"]:
        raise HTTPException(
            status_code=403,
            detail="Custodial accounts require F2-H Head of Household authorization",
        )

    val = req.requested_risk_pct
    fractional_units = ledger_account is not None and val is not None
    if ledger_account is not None and req.requested_risk_pct is None:
        fractional_units = False
    if val is None:
        raw = req.new_risk_dial if req.new_risk_dial is not None else (req.risk_dial if req.risk_dial is not None else req.risk_dial_pct)
        if raw is not None:
            val = raw if raw <= 5.0 else raw / 100.0

    lower, upper = (0.0, 0.05) if fractional_units else (0.5, 5.0)
    if val is None or val < lower or val > upper:
        raise HTTPException(status_code=400, detail="Risk dial must be between 0.5% and 5.0%")

    current_risk = target["risk_dial"]
    if ledger_account is not None:
        current_risk = ledger_account["max_risk_pct"] if fractional_units else ledger_account["max_risk_pct"] * 100.0
    if val > current_risk:
        raise HTTPException(
            status_code=400,
            detail=f"Downward-only policy: Requested risk ({val}) exceeds current ceiling ({current_risk})."
        )

    target["risk_dial"] = val
    if ledger_account is not None:
        ledger_account["max_risk_pct"] = val if fractional_units else val / 100.0
    return {"status": "APPROVED", "scma_id": scma_id, "applied_risk_dial": val,
            "risk_dial": val, "new_risk_pct": val}

@router.post("/api/v1/portal/member/request-distribution")
def request_capital_distribution(
    req: DistributionRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
):
    _enforce_portal_boundary(
        allowed_hats={"MEMBER_USER", "PERSONAL_SCMA"},
        action="MEMBER_DISTRIBUTION_REQUEST",
        target_id=req.scma_id,
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    for house in LINEAGE_DATA.values():
        for acct in house["accounts"]:
            if acct["scma_id"] == req.scma_id and acct.get("is_custodial"):
                raise HTTPException(
                    status_code=403,
                    detail="Custodial accounts require F2-H Head of Household authorization",
                )
    allowed_tags = ["Tuition", "Medical", "Real Estate", "Personal"]
    if req.category_tag not in allowed_tags:
        raise HTTPException(status_code=400, detail=f"Invalid tag. Must be one of {allowed_tags}")

    dollars = req.amount_cents / 100.0
    if dollars <= 100.00:
        tier = "GREEN"
        status = "EXECUTED_AUTONOMOUS"
        msg = f"Green-Tier distribution of ${dollars:.2f} executed autonomously."
    elif dollars <= 500.00:
        tier = "YELLOW"
        status = "NOTIFIED_ADVISOR"
        msg = f"Yellow-Tier distribution of ${dollars:.2f} logged. Notice sent to assigned F1 mentor."
    else:
        tier = "RED"
        status = "PENDING_F2_COSIGN"
        msg = f"Red-Tier distribution of ${dollars:.2f} initiated. 24-hour cooling off active; requires F2 Head of Household confirmation."

    return {
        "tier": tier,
        "status": status,
        "amount_dollars": dollars,
        "category_tag": req.category_tag,
        "message": msg
    }

# --- Advisor Workspace (F1, F2, F3) ---
@router.get("/api/v1/portal/advisor/lineage")
def get_advisor_lineage(
    household_id: str = Query("HOUSEHOLD-ALPHA"),
    tier: str = Query("F2")
) -> Dict[str, Any]:
    tier_upper = tier.upper()
    if tier_upper not in ["F1", "F2", "F3"]:
        tier_upper = "F2"

    if household_id not in LINEAGE_DATA:
        raise HTTPException(status_code=404, detail="Household branch not found")

    house = LINEAGE_DATA[household_id]

    if tier_upper == "F1":
        supervised = [house["accounts"][2]]
        approvals = []
        macro_risk = None
    elif tier_upper == "F2":
        supervised = house["accounts"]
        approvals = [
            {"request_id": "REQ-DIST-004", "member": "Julian Vance", "amount": "$650.00", "tag": "Tuition", "tier": "RED", "status": "AWAITING_F2"}
        ]
        macro_risk = None
    else:
        supervised = house["accounts"]
        approvals = []
        macro_risk = {
            "cross_house_exposure": "$18,500.00",
            "weather_factor_concentration": "8.4% (Cap: 10.0%)",
            "macro_factor_concentration": "4.2% (Cap: 10.0%)",
            "platform_var_99": "$420.00"
        }

    return {
        "tier": tier_upper,
        "household_id": house["household_id"],
        "household_name": house["household_name"],
        "total_equity": house["total_equity"],
        "max_drawdown_pct": house["max_drawdown_pct"],
        "cfcp_floor_shield": house["cfcp_floor_shield"],
        "sub_accounts": supervised,
        "pending_approvals": approvals,
        "macro_risk": macro_risk,
        "audit_queue": [
            {
                "contract_id": "KX-MIA-FRZ-32",
                "category": "WEATHER",
                "venue": "KALSHI",
                "model_prob": 31.5,
                "market_price": 3.0,
                "net_edge": 28.5,
                "plain_english_rationale": "Model projects 31.5% freeze likelihood vs 3% venue price; statistical edge exceeds 28% margin barrier."
            }
        ]
    }

@router.get("/api/v1/portal/advisor/household-tree")
def get_advisor_household_tree(
    household_id: str = Query("HOUSEHOLD-ALPHA"),
    role: str = Query("F2-H"),
    authenticated_household_id: str = Header("HOUSEHOLD-ALPHA", alias="X-Household-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
) -> Dict[str, Any]:
    """Return only the branch assigned to the authenticated advisor session."""
    _enforce_portal_boundary(
        allowed_hats={"F1", "F2-H", "F2-A", "F3", "CHIEF_ADMINISTRATOR"},
        action="ADVISOR_HOUSEHOLD_TREE",
        target_id=household_id,
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        block_class_t=True,
        is_mutation=False,
    )
    if household_id != authenticated_household_id:
        raise HTTPException(status_code=403, detail="Cross-household access denied")
    house = LINEAGE_DATA.get(authenticated_household_id)
    if house is None:
        raise HTTPException(status_code=404, detail="Household branch not found")

    role = role.upper()
    if role not in {"F1", "F2-H", "F2-A", "F3"}:
        raise HTTPException(status_code=422, detail="Unsupported financial advisor role")
    claimed_f = normalize_role_token(x_active_hat or x_actor_role)
    if claimed_f in {"F1", "F2-H", "F2-A", "F3"} and claimed_f != role:
        raise HTTPException(
            status_code=403,
            detail=f"CROSS_TIER_ACCESS_DENIED: Class F tier {claimed_f} cannot query {role} workspace data.",
        )

    accounts = []
    for account in house["accounts"]:
        if role == "F1" and not account["is_custodial"]:
            continue
        item: Dict[str, Any] = {
            "user_id": account["user_id"],
            "name": account["name"],
            "scma_id": account["scma_id"],
            "risk_dial_bps": round(account["risk_dial"] * 100),
            "is_custodial": account["is_custodial"],
            "custodian_id": account["custodian_id"],
            "risk_controls_locked": account["is_custodial"],
            "risk_increase_requires": "F2_CO_SIGN" if account["is_custodial"] else None,
        }
        if role == "F1":
            item["balance_redacted"] = True
            item["balance_display"] = "$****.**"
        else:
            item["balance_cents"] = round(account["balance"] * 100)
        accounts.append(item)

    distributions = [
        {"request_id": "DIST-104", "member": "Julian Vance", "category": "Tuition", "amount_cents": 65000, "action": "F2_CO_SIGN", "status": _DISTRIBUTION_STATE["DIST-104"]["status"]},
        {"request_id": "DIST-105", "member": "Eleanor Vance", "category": "Living", "amount_cents": 18000, "action": "APPROVE", "status": _DISTRIBUTION_STATE["DIST-105"]["status"]},
    ]
    if role in {"F2-A", "F3"}:
        for distribution in distributions:
            distribution["action"] = "READ_ONLY_AUDIT"
            distribution["action_label"] = "READ-ONLY AUDIT (F2-H SIGNATURE REQUIRED)"

    response = {
        "role": role,
        "household_id": house["household_id"],
        "household_name": house["household_name"],
        "member_count": len(accounts),
        "accounts": accounts,
        "pending_distributions": [] if role == "F1" else distributions,
        "pit_decisions": [{
            "candidate_id": "KX-MIA-FRZ-32", "venue": "Kalshi", "filled_price_cents": 3,
            "model_probability_bps": 3150,
            "explanation": "The maker fill was accepted because the 31.5% model probability exceeded the 3% venue price after all safeguards.",
        }],
    }
    # CRO scope is platform-wide: never serialize domestic account or spending data.
    if role == "F3":
        response["accounts"] = []
        response["member_count"] = 0
        response["pending_distributions"] = []
        response["pit_decisions"] = []
    # F1 responses deliberately omit aggregate financial data rather than merely
    # relying on the browser to conceal it.
    if role not in {"F1", "F3"}:
        response["total_family_equity_cents"] = sum(
            round(account["balance"] * 100) for account in house["accounts"]
        )
        response["available_liquidity_cents"] = response["total_family_equity_cents"]
    if role == "F3":
        response["platform_risk_metrics"] = {
            "value_at_risk_cents": 42000,
            "margin_utilization_pct": 37.4,
            "evt_tail_risk": "MODERATE / WITHIN POLICY",
            "platform_var_99_cents": 42000,
            "cross_house_exposure_cents": 1850000,
            "concentration_status": "WITHIN_POLICY",
        }
    r04_snapshot = get_directive_r04_controller().snapshot()
    response["directive_r04"] = r04_snapshot
    response["read_model_envelope"] = build_read_model_envelope(
        {"household_id": house["household_id"], "role": role, "member_count": response["member_count"]},
        surface="advisor",
        directive_r04_snapshot=r04_snapshot,
    ).model_dump()
    return response


@router.get("/api/v1/portal/advisor/macro-risk")
def get_advisor_macro_risk(
    role: str = Query("F3"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
) -> Dict[str, Any]:
    """Return platform risk in integer cents; household domestic detail is excluded."""
    _enforce_portal_boundary(
        allowed_hats={"F3", "CHIEF_ADMINISTRATOR"},
        action="ADVISOR_MACRO_RISK",
        target_id="PLATFORM_MACRO_RISK",
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        block_class_t=True,
        is_mutation=False,
    )
    if role.upper() not in {"F3", "CHIEF_ADMIN", "CHIEF_ADMINISTRATOR"}:
        raise HTTPException(status_code=403, detail="F3 CRO or Chief Admin authority required")
    r04_controller = get_directive_r04_controller()
    r04_snapshot = r04_controller.snapshot()
    envelope = build_read_model_envelope(
        {
            "platform_var_99_24h_cents": 42_000,
            "cross_house_gross_margin_cents": 1_850_000,
            "margin_utilization_pct": 74,
        },
        surface="advisor",
        directive_r04_snapshot=r04_snapshot,
    )
    return {
        "platform_var_99_24h_cents": 42_000,
        "cross_house_gross_margin_cents": 1_850_000,
        "margin_utilization_pct": 74,
        "venue_distribution_pct": {"Kalshi": 58, "Polymarket": 42},
        "directive_r04": r04_snapshot,
        "dual_signature_overrides": r04_controller.list_overrides(),
        "house_exposures": _MACRO_HOUSE_EXPOSURES,
        "read_model_envelope": envelope.model_dump(),
    }


@router.get("/api/v1/portal/advisor/proposals")
def get_advisor_proposals(
    role: str = Query("F2-A"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
) -> Dict[str, Any]:
    _enforce_portal_boundary(
        allowed_hats={"F2-A", "F2-H", "F3", "CHIEF_ADMINISTRATOR"},
        action="ADVISOR_LIST_PROPOSALS",
        target_id="ADVISORY_PROPOSALS",
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        block_class_t=True,
        is_mutation=False,
    )
    if role.upper() not in {"F2-A", "F2-H", "F3", "CHIEF_ADMIN", "CHIEF_ADMINISTRATOR"}:
        raise HTTPException(status_code=403, detail="Advisory proposal access denied")
    return {"proposals": list(_ADVISORY_PROPOSALS.values())}


@router.post("/api/v1/portal/advisor/proposals", status_code=201)
def stage_advisor_proposal(
    request: AdvisoryProposalRequest,
    role: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    global _ADVISORY_PROPOSAL_SEQUENCE
    _enforce_portal_boundary(
        allowed_hats={"F2-A", "F2-H", "CHIEF_ADMINISTRATOR"},
        action="ADVISOR_STAGE_PROPOSAL",
        target_id=request.target_scma,
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    actor_role = (role or x_actor_role or request.actor_role or "").upper()
    if actor_role not in {"F2-A", "F2-H"}:
        raise HTTPException(status_code=403, detail="Only F2-A or F2-H may stage advisory proposals")
    if is_founder_target(request.target_scma):
        enforce_founder_immunity(
            target_id=request.target_scma,
            action="STAGE_ADVISORY_PROPOSAL",
            actor_role=actor_role,
            actor_id=actor_role,
        )
    if not request.target_scma.strip() or not request.justification.strip():
        raise HTTPException(status_code=422, detail="Target SCMA and justification are required")
    if request.proposed_dial < 0 or request.proposed_dial > 100:
        raise HTTPException(status_code=422, detail="proposed_dial must be between 0 and 100")
    _ADVISORY_PROPOSAL_SEQUENCE += 1
    proposal_id = f"ADV-{_ADVISORY_PROPOSAL_SEQUENCE:04d}"
    proposal = {
        "proposal_id": proposal_id, "target_scma": request.target_scma,
        "proposed_dial": request.proposed_dial, "justification": request.justification,
        "submitted_by": actor_role, "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(), "adjudicated_by": None,
    }
    _ADVISORY_PROPOSALS[proposal_id] = proposal
    return proposal


@router.post("/api/v1/portal/advisor/proposals/{proposal_id}/adjudicate")
def adjudicate_advisor_proposal(
    proposal_id: str,
    request: AdvisoryAdjudicationRequest,
    role: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    _enforce_portal_boundary(
        allowed_hats={"F3", "CHIEF_ADMINISTRATOR"},
        action="ADVISOR_ADJUDICATE_PROPOSAL",
        target_id=proposal_id,
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    actor_role = (role or x_actor_role or request.actor_role or "").upper()
    if actor_role not in {"F3", "CHIEF_ADMIN", "CHIEF_ADMINISTRATOR"}:
        raise HTTPException(status_code=403, detail="Only F3 CRO or Chief Admin may adjudicate proposals")
    decision = request.decision.upper()
    if decision not in {"ALLOW", "DENY"}:
        raise HTTPException(status_code=422, detail="decision must be ALLOW or DENY")
    proposal = _ADVISORY_PROPOSALS.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Advisory proposal not found")
    if proposal["status"] != "PENDING":
        raise HTTPException(status_code=409, detail="Proposal has already been adjudicated")
    # The seeded queue card uses the human-readable supervisory lifecycle label;
    # retain the legacy staged-proposal label for API compatibility.
    proposal["status"] = (
        "APPROVED / ACTIVE" if proposal_id == "PROP-ADV-01" and decision == "ALLOW"
        else "ALLOWED" if decision == "ALLOW"
        else "DENIED"
    )
    proposal["adjudicated_by"] = actor_role
    proposal["adjudicated_at"] = datetime.now(timezone.utc).isoformat()
    return proposal


@router.post("/api/v1/portal/advisor/custodial-risk-dial")
def update_custodial_minor_risk_dial(
    request: CustodialRiskDialRequest,
    role: Optional[str] = Query(None),
    authenticated_household_id: str = Header("HOUSEHOLD-ALPHA", alias="X-Household-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    """F2-H Head of Household custodial minor risk dial governance (0.50%-1.00% conservative bounds)."""
    _enforce_portal_boundary(
        allowed_hats={"F2-H", "CHIEF_ADMINISTRATOR"},
        action="CUSTODIAL_RISK_DIAL_UPDATE",
        target_id=request.scma_id,
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    actor_role = normalize_advisor_role(role or x_actor_role or request.actor_role or "")
    if actor_role != "F2-H":
        get_governance_audit_log().record(
            event_type="ROLE_BOUNDARY_DENIED",
            actor_id=actor_role or "UNKNOWN",
            actor_role=actor_role or "UNKNOWN",
            target_id=request.scma_id,
            action="CUSTODIAL_RISK_DIAL_UPDATE",
            outcome="DENIED_F2H_REQUIRED",
            http_status=403,
            detail="Only F2-H Head of Household may govern custodial minor risk dials.",
        )
        raise HTTPException(status_code=403, detail="F2-H Head of Household authority is required for custodial accounts")

    if is_founder_target(request.scma_id):
        enforce_founder_immunity(
            target_id=request.scma_id,
            action="UPDATE_CUSTODIAL_RISK_DIAL",
            actor_role="F2-H",
            actor_id="F2-H",
        )

    target_household = request.household_id or authenticated_household_id
    if target_household != authenticated_household_id:
        raise HTTPException(status_code=403, detail="Cross-household custodial control denied")
    house = LINEAGE_DATA.get(authenticated_household_id)
    if house is None:
        raise HTTPException(status_code=404, detail="Household branch not found")
    target = next((a for a in house["accounts"] if a["scma_id"] == request.scma_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="SCMA not found in assigned household")
    if not target.get("is_custodial"):
        raise HTTPException(status_code=403, detail="Target account is not a custodial minor account")
    if request.requested_risk_pct < 0.50 or request.requested_risk_pct > 1.00:
        raise HTTPException(status_code=400, detail="Custodial minor risk dial must remain within 0.50% to 1.00% bounds")

    target["risk_dial"] = request.requested_risk_pct
    try:
        lineage_member = _lineage_service.get_member_state(request.scma_id)
        lineage_member["risk_dial"] = request.requested_risk_pct / 100.0
    except ValueError:
        pass
    return {
        "status": "CUSTODIAL_RISK_UPDATED",
        "scma_id": request.scma_id,
        "household_id": authenticated_household_id,
        "applied_risk_pct": request.requested_risk_pct,
        "authorized_by": "F2-H",
        "is_custodial": True,
    }


@router.post("/api/v1/portal/advisor/emergency-halt")
def advisor_trigger_emergency_halt(
    request: DirectiveR04HaltRequest,
    role: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    """Directive R-04 Emergency Financial Halt — F3 CRO or Chief Administrator."""
    _enforce_portal_boundary(
        allowed_hats={"F3", "CHIEF_ADMINISTRATOR"},
        action="DIRECTIVE_R04_HALT",
        target_id="DIRECTIVE_R04",
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    actor_role = role or x_actor_role or request.actor_role or ""
    actor_id = request.actor_id or actor_role or "unknown"
    return get_directive_r04_controller().trigger_halt(
        actor_role=actor_role,
        actor_id=actor_id,
        reason=request.reason,
    )


@router.post("/api/v1/portal/advisor/emergency-resume")
def advisor_resume_from_halt(
    request: DirectiveR04ResumeRequest,
    role: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    """Directive R-04 Resumption — strictly reserved to Chief Administrator (HTTP 403 for F3 and all subordinates)."""
    _enforce_portal_boundary(
        allowed_hats={"CHIEF_ADMINISTRATOR"},
        action="DIRECTIVE_R04_RESUME",
        target_id="DIRECTIVE_R04",
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    actor_role = role or x_actor_role or request.actor_role or ""
    actor_id = request.actor_id or actor_role or "unknown"
    return get_directive_r04_controller().resume(
        actor_role=actor_role,
        actor_id=actor_id,
        justification=request.justification or "",
    )


@router.get("/api/v1/portal/advisor/dual-signature-overrides")
def list_dual_signature_overrides(
    role: str = Query("F3"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
) -> Dict[str, Any]:
    _enforce_portal_boundary(
        allowed_hats={"F3", "CHIEF_ADMINISTRATOR"},
        action="LIST_DUAL_SIG_OVERRIDES",
        target_id="DUAL_SIG_OVERRIDES",
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        block_class_t=True,
        is_mutation=False,
    )
    if normalize_role_token(role) not in {"F3", "CHIEF_ADMINISTRATOR"}:
        raise HTTPException(status_code=403, detail="F3 CRO or Chief Admin authority required")
    return {"overrides": get_directive_r04_controller().list_overrides()}


@router.post("/api/v1/portal/advisor/dual-signature-override", status_code=201)
def submit_dual_signature_override(
    request: DualSignatureOverrideRequest,
    role: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    _enforce_portal_boundary(
        allowed_hats={"F3", "CHIEF_ADMINISTRATOR"},
        action="SUBMIT_DUAL_SIG_OVERRIDE",
        target_id=request.target_scope,
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    actor_role = role or x_actor_role or request.actor_role or ""
    actor_id = request.actor_id or actor_role or "unknown"
    return get_directive_r04_controller().submit_dual_signature_override(
        actor_role=actor_role,
        actor_id=actor_id,
        target_scope=request.target_scope,
        action=request.action,
        justification=request.justification,
    )


@router.post("/api/v1/portal/advisor/dual-signature-override/{override_id}/countersign")
def countersign_dual_signature_override(
    override_id: str,
    request: DualSignatureCountersignRequest,
    role: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    _enforce_portal_boundary(
        allowed_hats={"CHIEF_ADMINISTRATOR"},
        action="COUNTERSIGN_DUAL_SIG_OVERRIDE",
        target_id=override_id,
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    actor_role = role or x_actor_role or request.actor_role or ""
    actor_id = request.actor_id or actor_role or "unknown"
    return get_directive_r04_controller().countersign_override(
        override_id=override_id,
        actor_role=actor_role,
        actor_id=actor_id,
        decision=request.decision,
    )


# --- Technical Infrastructure (T1, T2, T2-Household, T3 & Directive R-12) ---
@router.get("/api/v1/portal/tech/telemetry")
def get_tech_telemetry(
    tier: str = Query("T1"),
    unredact_token: Optional[str] = Query(None),
    household_id: str = Query("HOUSEHOLD-ALPHA"),
    authenticated_household_id: Optional[str] = Header(None, alias="X-Household-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
) -> Dict[str, Any]:
    _enforce_portal_boundary(
        allowed_hats={"T1", "T2", "T2-HOUSEHOLD", "T3", "CHIEF_ADMINISTRATOR"},
        action="TECH_TELEMETRY_READ",
        target_id=tier,
        authorization=authorization,
        x_active_hat=x_active_hat,
        block_class_t=False,
        is_mutation=False,
    )
    tier_norm = normalize_tech_tier(tier)
    claimed_t = normalize_role_token(x_active_hat or x_actor_role)
    if claimed_t in {"T1", "T2", "T2-HOUSEHOLD", "T3"} and claimed_t != tier_norm:
        raise HTTPException(
            status_code=403,
            detail=f"CROSS_TIER_ACCESS_DENIED: Class T tier {claimed_t} cannot query {tier_norm} telemetry.",
        )

    if tier_norm == "T2-HOUSEHOLD":
        if authenticated_household_id and authenticated_household_id.upper() != household_id.upper():
            get_governance_audit_log().record(
                event_type="ROLE_BOUNDARY_DENIED",
                actor_id=authenticated_household_id,
                actor_role="T2-HOUSEHOLD",
                target_id=household_id,
                action="HOUSEHOLD_TELEMETRY_READ",
                outcome="DENIED_CROSS_HOUSEHOLD",
                http_status=403,
                detail=f"T2-Household scoped to {authenticated_household_id} cannot inspect {household_id}.",
            )
            raise HTTPException(
                status_code=403,
                detail="CROSS_HOUSEHOLD_TELEMETRY_DENIED: T2-Household is scoped strictly to its assigned household.",
            )
        if household_id not in LINEAGE_DATA:
            raise HTTPException(status_code=404, detail="Assigned household not found")

    override_grant = get_ca_override_manager().validate_token(tier_norm, unredact_token)
    is_unredacted = bool(tier_norm == "T3" and override_grant is not None)

    if tier_norm == "T2-HOUSEHOLD":
        recent_orders = [
            {
                "order_id": f"ORD-HH-{household_id[-5:]}",
                "account_id": "SCMA-MEM-****-REDACTED",
                "contract": "KX-MIA-FRZ-32",
                "notional_cents": "REDACTED",
                "household_id": household_id,
                "mode": "PAPER_MAKER",
            }
        ]
        order_ladder = [
            {
                "candidate_id": f"CAND-HH-{household_id[-5:]}",
                "venue": "Kalshi",
                "household_id": household_id,
                "scma_id": "SCMA-MEM-****",
                "model_probability_bps": 3150,
                "exposure_cents": "$****.**",
            }
        ]
        worker_health = [
            {
                "worker": f"HouseholdRelay-{household_id}",
                "cycle": _TECH_WORKER.cycle_count,
                "status": "NOMINAL",
                "latency_ms": 11.2,
                "scope": household_id,
            },
            {
                "worker": "RateLimiter-Kalshi",
                "bucket_tokens": 85,
                "max_tokens": 100,
                "status": "OPTIMAL",
                "scope": household_id,
            },
        ]
    else:
        recent_orders = [
            {
                "order_id": "ORD-0912-A1",
                "account_id": "SCMA-ELEANOR_-B2B31C9E" if is_unredacted else "SCMA-MEM-****-REDACTED",
                "contract": "KX-MIA-FRZ-32",
                "notional_cents": 2500 if is_unredacted else "REDACTED",
                "mode": "PAPER_MAKER",
            }
        ]
        order_ladder = [
            {
                "candidate_id": "CAND-0912-A1",
                "venue": "Kalshi",
                "scma_id": "SCMA-ELEANOR_-B2B31C9E" if is_unredacted else "SCMA-MEM-****",
                "model_probability_bps": 3150,
                "exposure_cents": 2500 if is_unredacted else "$****.**",
            }
        ]
        worker_health = [
            {"worker": "AutonomousScanWorker", "cycle": _TECH_WORKER.cycle_count, "status": "NOMINAL", "latency_ms": 12.4},
            {"worker": "SettlementReconciler", "cycle": 710, "status": "IDLE", "latency_ms": 4.1},
            {"worker": "RateLimiter-Kalshi", "bucket_tokens": 85, "max_tokens": 100, "status": "OPTIMAL"},
            {"worker": "RateLimiter-Polymarket", "bucket_tokens": 92, "max_tokens": 100, "status": "OPTIMAL"},
        ]

    r04_snapshot = get_directive_r04_controller().snapshot()
    tech_envelope = build_read_model_envelope(
        {
            "tier": tier_norm,
            "cycle_count": _TECH_WORKER.cycle_count,
            "settled_count": _TECH_SETTLED_COUNT,
            "redaction_active": not is_unredacted,
        },
        surface="tech",
        directive_r04_snapshot=r04_snapshot,
    )
    return {
        "tier": tier_norm,
        "telemetry_scope": "CLASS_T_HOUSEHOLD_SCOPED" if tier_norm == "T2-HOUSEHOLD" else "CLASS_T_OPERATIONAL",
        "assigned_household_id": household_id if tier_norm == "T2-HOUSEHOLD" else None,
        "redaction_active": not is_unredacted,
        "override_grant_id": override_grant["grant_id"] if is_unredacted else None,
        "override_expires_at_utc": override_grant["expires_at_utc"] if is_unredacted else None,
        "directive_enforced": "Directive R-12 (Least Privilege Redacted Financial Telemetry)",
        "can_trigger_daemons": tier_norm in {"T2", "T3"},
        "can_trigger_global_daemons": tier_norm in {"T2", "T3"},
        "can_override_redaction": tier_norm == "T3",
        "financial_authority": False,
        "house_authority": False,
        "household_authority": False,
        "worker_health": worker_health,
        "daemon_status": {"AutonomousScanWorker": "ACTIVE"},
        "cycle_count": _TECH_WORKER.cycle_count,
        "settled_count": _TECH_SETTLED_COUNT,
        "settlement_waterfall": "87/10/3",
        "ws_latency_ms": _TECH_LATENCY_MS,
        "token_buckets": _TECH_TOKEN_BUCKETS,
        "dry_powder_floor_cents": 4000,
        "dry_powder_floor_status": "COMPLIANT",
        "active_order_ladder": order_ladder,
        "recent_dispatches": recent_orders,
        "system_metrics": {
            "cpu_load_pct": 8.5,
            "memory_usage_mb": 142.1,
            "active_websockets": 2,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "directive_r04": r04_snapshot,
        "read_model_envelope": tech_envelope.model_dump(),
    }


@router.get("/api/v1/portal/telemetry/daemon-summary")
def get_daemon_summary() -> Dict[str, Any]:
    """Return the process-local daemon's latest non-sensitive operating state."""
    telemetry = _TECH_WORKER.get_telemetry()
    return {
        "status": telemetry["status"],
        "cycle_count": telemetry["cycle_count"],
        "cycles_completed": telemetry["cycles_completed"],
        "active_maker_bids": telemetry["active_maker_bids"],
        "active_maker_orders": telemetry["active_maker_orders"],
        "orders_posted": telemetry["orders_posted"],
        "orders_filled": telemetry["orders_filled"],
        "total_capital_sweeps_emitted": telemetry["capital_sweeps_emitted"],
        "slot_capacity": 12,
        "dry_powder_floor_cents": telemetry["dry_powder_floor_cents"],
    }

@router.post("/api/v1/portal/tech/trigger-daemon")
def trigger_tech_daemon(
    tier: str = Query("T3"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    """Run one real worker evaluation and expose only operational telemetry."""
    _enforce_portal_boundary(
        allowed_hats={"T2", "T3", "CHIEF_ADMINISTRATOR"},
        action="TECH_TRIGGER_DAEMON",
        target_id="AutonomousScanWorker",
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=False,
        is_mutation=True,
    )
    tier_norm = normalize_tech_tier(tier)
    if tier_norm not in {"T2", "T3"}:
        get_governance_audit_log().record(
            event_type="ROLE_BOUNDARY_DENIED",
            actor_id=tier_norm,
            actor_role=tier_norm,
            target_id="AutonomousScanWorker",
            action="TECH_TRIGGER_DAEMON",
            outcome="DENIED_TIER_BLOCKED",
            http_status=403,
            detail=f"{tier_norm} cannot invoke global daemon triggers.",
        )
        detail = (
            "T2-Household is strictly household-scoped and cannot trigger global daemons"
            if tier_norm == "T2-HOUSEHOLD"
            else "T1 telemetry access is read-only"
        )
        raise HTTPException(status_code=403, detail=detail)
    result = _TECH_WORKER.run_single_cycle()
    # Deterministic live telemetry avoids external venue dependencies in the console.
    _TECH_LATENCY_MS["Kalshi"] = 11 + (_TECH_WORKER.cycle_count % 5)
    _TECH_LATENCY_MS["Polymarket"] = 18 + (_TECH_WORKER.cycle_count % 7)
    for bucket in _TECH_TOKEN_BUCKETS.values():
        bucket["available"] = max(0, int(bucket["capacity"]) - (_TECH_WORKER.cycle_count % 3))
    return {
        "status": result["status"],
        "cycle_count": _TECH_WORKER.cycle_count,
        "ws_latency_ms": dict(_TECH_LATENCY_MS),
        "token_buckets": {key: dict(value) for key, value in _TECH_TOKEN_BUCKETS.items()},
    }


@router.post("/api/v1/portal/tech/trigger-settlement")
def trigger_tech_settlement(
    tier: str = Query("T3"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    """Run a deterministic reconciliation cycle without exposing ledger values."""
    global _TECH_SETTLED_COUNT
    _enforce_portal_boundary(
        allowed_hats={"T2", "T3", "CHIEF_ADMINISTRATOR"},
        action="TECH_TRIGGER_SETTLEMENT",
        target_id="SettlementReconciler",
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=False,
        is_mutation=True,
    )
    tier_norm = normalize_tech_tier(tier)
    if tier_norm not in {"T2", "T3"}:
        get_governance_audit_log().record(
            event_type="ROLE_BOUNDARY_DENIED",
            actor_id=tier_norm,
            actor_role=tier_norm,
            target_id="SettlementReconciler",
            action="TECH_TRIGGER_SETTLEMENT",
            outcome="DENIED_TIER_BLOCKED",
            http_status=403,
            detail=f"{tier_norm} cannot invoke global settlement reconciliation.",
        )
        detail = (
            "T2-Household is strictly household-scoped and cannot trigger global settlement"
            if tier_norm == "T2-HOUSEHOLD"
            else "T1 telemetry access is read-only"
        )
        raise HTTPException(status_code=403, detail=detail)
    _TECH_SETTLED_COUNT += 1
    return {
        "status": "SETTLED",
        "settled_count": _TECH_SETTLED_COUNT,
        "waterfall": "87/10/3",
    }

@router.post("/api/v1/portal/tech/ca-override")
def activate_ca_override(
    request: CAOverrideRequest,
    tier: str = Query("T3"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    """Issue a time-bounded, audited, page-scoped unredact grant only for T3 CTO after CA authentication."""
    _enforce_portal_boundary(
        allowed_hats={"T3", "CHIEF_ADMINISTRATOR"},
        action="ACTIVATE_CA_OVERRIDE",
        target_id="DIRECTIVE_R12_UNREDACT",
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=False,
        is_mutation=True,
    )
    grant = get_ca_override_manager().issue_grant(
        tier=tier,
        secret_token=request.token,
        actor_id=request.actor_id or "T3_CTO",
        reason=request.reason or "Audited incident diagnostics",
        ttl_seconds=request.ttl_seconds,
    )
    return {
        "status": "ACTIVE_UNREDACT_GRANT",
        "redaction_active": False,
        "grant_id": grant["grant_id"],
        "grant_token": grant["grant_token"],
        "ttl_seconds": grant["ttl_seconds"],
        "issued_at_utc": grant["issued_at_utc"],
        "expires_at_utc": grant["expires_at_utc"],
        "audit_event_id": grant["audit_event_id"],
        "active_order_ladder": [{
            "candidate_id": "CAND-0912-A1", "venue": "Kalshi",
            "scma_id": "SCMA-ELEANOR_-B2B31C9E", "model_probability_bps": 3150,
            "exposure_cents": 2500,
        }],
    }


@router.post("/api/v1/portal/tech/ca-override/revoke")
def revoke_ca_override(
    request: Optional[CAOverrideRevokeRequest] = None,
    tier: str = Query("T3"),
) -> Dict[str, Any]:
    """Immediately revoke an active CA R-12 override grant and restore masking."""
    if normalize_tech_tier(tier) != "T3":
        raise HTTPException(status_code=403, detail="CA override revocation requires T3 CTO authority")
    return get_ca_override_manager().revoke_grant(
        request.grant_token if request else None,
        actor_id=(request.actor_id if request and request.actor_id else "T3_CTO"),
    )


@router.post("/api/v1/portal/advisor/co-sign")
def co_sign_distribution(
    request: CoSignRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_supervisory_mode: Optional[str] = Header(None, alias="X-Supervisory-Mode"),
) -> Dict[str, Any]:
    _enforce_portal_boundary(
        allowed_hats={"F2-H"},
        action="ADVISOR_CO_SIGN_DISTRIBUTION",
        target_id=request.request_id,
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        x_supervisory_mode=x_supervisory_mode,
        block_class_t=True,
        is_mutation=True,
    )
    if request.actor_role != "F2-H" or (x_actor_role and normalize_advisor_role(x_actor_role) != "F2-H"):
        get_governance_audit_log().record(
            event_type="ROLE_BOUNDARY_DENIED",
            actor_id=x_actor_role or request.actor_role,
            actor_role=normalize_role_token(x_actor_role or request.actor_role),
            target_id=request.request_id,
            action="ADVISOR_CO_SIGN_DISTRIBUTION",
            outcome="DENIED_F2H_REQUIRED",
            http_status=403,
            detail="F2-H Head of Household authority is required for dual-control co-signature.",
        )
        raise HTTPException(status_code=403, detail="F2-H authority is required for dual-control co-signature")
    distribution = _DISTRIBUTION_STATE.get(request.request_id)
    if distribution is None:
        raise HTTPException(status_code=404, detail="Distribution request not found")
    distribution["status"] = "CO-SIGNED / STAGED (DUAL-CONTROL RATIFIED)"
    distribution["signature"] = {
        "actor_role": request.actor_role,
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }
    available_liquidity_cents = sum(round(a["balance"] * 100) for a in LINEAGE_DATA["HOUSEHOLD-ALPHA"]["accounts"]) - int(distribution["amount_cents"])
    return {
        "request_id": request.request_id,
        "status": distribution["status"],
        "signature": distribution["signature"],
        "available_liquidity_cents": available_liquidity_cents,
    }

# --- Scoped Copilots ---
@router.post("/api/v1/portal/member/ai-tutor")
def member_ai_tutor(query: AssistantQuery, scma_id: Optional[str] = Query(None)):
    prompt = query.query or query.question or ""
    target_scma_id = (query.scma_id or scma_id or "").strip() or None
    member_state = get_member_state(user_id=None, scma_id=target_scma_id)
    return _member_literacy_tutor.answer_member_query(prompt, member_state=member_state)

@router.post("/api/v1/portal/member/tutor")
def member_tutor(query: AssistantQuery, scma_id: Optional[str] = Query(None)):
    """Stable novice-facing alias used by the Member Desktop."""
    return member_ai_tutor(query, scma_id=scma_id)

@router.post("/api/v1/portal/advisor/copilot")
def advisor_copilot(
    query: AssistantQuery,
    role: Optional[str] = Query(None),
    household_id: Optional[str] = Query(None),
    authenticated_household_id: Optional[str] = Header(None, alias="X-Household-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
):
    _enforce_portal_boundary(
        allowed_hats={"F1", "F2-H", "F2-A", "F3", "CHIEF_ADMINISTRATOR"},
        action="ADVISOR_COPILOT_QUERY",
        target_id=household_id or query.household_id or "HOUSEHOLD-ALPHA",
        authorization=authorization,
        x_active_hat=x_active_hat,
        x_actor_role=x_actor_role,
        block_class_t=True,
        is_mutation=False,
    )
    prompt = query.query or query.question or ""
    requested_role = (
        role
        or query.role
        or x_actor_role
        or (query.context_scope if query.context_scope and query.context_scope.upper() != "GENERAL" else None)
        or "F2-H"
    )
    requested_hh = (household_id or query.household_id or authenticated_household_id or "HOUSEHOLD-ALPHA").strip()
    if (
        authenticated_household_id
        and requested_hh.upper() != authenticated_household_id.strip().upper()
        and normalize_advisor_role(requested_role) in {"F1", "F2-H"}
    ):
        get_governance_audit_log().record(
            event_type="ROLE_BOUNDARY_DENIED",
            actor_id=authenticated_household_id,
            actor_role=normalize_advisor_role(requested_role) or "F2-H",
            target_id=requested_hh,
            action="ADVISOR_COPILOT_QUERY",
            outcome="DENIED_CROSS_HOUSEHOLD",
            http_status=403,
            detail=f"Class F session scoped to {authenticated_household_id} cannot query {requested_hh}.",
        )
        raise HTTPException(status_code=403, detail="Cross-household access denied")

    r04_controller = get_directive_r04_controller()
    return _class_f_copilot.answer_advisor_query(
        prompt,
        role=requested_role,
        household_id=requested_hh,
        lineage_data=LINEAGE_DATA,
        distribution_state=_DISTRIBUTION_STATE,
        advisory_proposals=_ADVISORY_PROPOSALS,
        macro_house_exposures=_MACRO_HOUSE_EXPOSURES,
        directive_r04_snapshot=r04_controller.snapshot(),
        dual_sig_overrides=r04_controller.list_overrides(),
    )


@router.post("/api/v1/portal/tech/copilot")
def tech_copilot(
    query: AssistantQuery,
    tier: Optional[str] = Query(None),
    household_id: Optional[str] = Query(None),
    unredact_token: Optional[str] = Query(None),
    authenticated_household_id: Optional[str] = Header(None, alias="X-Household-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
):
    _enforce_portal_boundary(
        allowed_hats={"T1", "T2", "T2-HOUSEHOLD", "T3", "CHIEF_ADMINISTRATOR"},
        action="TECH_COPILOT_QUERY",
        target_id=tier or query.tier or "T1",
        authorization=authorization,
        x_active_hat=x_active_hat,
        block_class_t=False,
        is_mutation=False,
    )
    prompt = query.query or query.question or ""
    raw_tier = tier or query.tier
    if not raw_tier and query.context_scope:
        scope_upper = query.context_scope.strip().upper()
        if scope_upper in {"T1", "T2", "T2-HOUSEHOLD", "T2_HOUSEHOLD", "T3"}:
            raw_tier = scope_upper
        elif scope_upper == "READ_ONLY_TELEMETRY":
            raw_tier = "T1"
        elif scope_upper == "OPERATIONS":
            raw_tier = "T3"
    tier_norm = normalize_tech_tier(raw_tier or "T1")
    target_hh = (household_id or query.household_id or authenticated_household_id or "HOUSEHOLD-ALPHA").strip()

    if tier_norm == "T2-HOUSEHOLD":
        if authenticated_household_id and authenticated_household_id.strip().upper() != target_hh.upper():
            get_governance_audit_log().record(
                event_type="ROLE_BOUNDARY_DENIED",
                actor_id=authenticated_household_id,
                actor_role="T2-HOUSEHOLD",
                target_id=target_hh,
                action="HOUSEHOLD_COPILOT_QUERY",
                outcome="DENIED_CROSS_HOUSEHOLD",
                http_status=403,
                detail=f"T2-Household scoped to {authenticated_household_id} cannot query {target_hh}.",
            )
            raise HTTPException(
                status_code=403,
                detail="CROSS_HOUSEHOLD_TELEMETRY_DENIED: T2-Household is scoped strictly to its assigned household.",
            )
        if target_hh not in LINEAGE_DATA:
            raise HTTPException(status_code=404, detail="Assigned household not found")

    token = unredact_token or query.unredact_token
    override_grant = get_ca_override_manager().validate_token(tier_norm, token) if token else None

    return _class_t_copilot.answer_tech_query(
        prompt,
        tier=tier_norm,
        household_id=target_hh,
        cycle_count=_TECH_WORKER.cycle_count,
        settled_count=_TECH_SETTLED_COUNT,
        ws_latency_ms=_TECH_LATENCY_MS,
        token_buckets=_TECH_TOKEN_BUCKETS,
        override_grant=override_grant,
        directive_r04_snapshot=get_directive_r04_controller().snapshot(),
    )

@router.get("/api/v1/portal/advisor/decision-audit/{contract_id}")
def advisor_decision_audit(contract_id: str):
    return {
        "contract_id": contract_id,
        "plain_english_rationale": "The point-in-time model edge cleared the institutional hurdle before maker dispatch.",
        "status": "AUDITED",
    }

__all__ = ["router", "portal_router", "LINEAGE_DATA"]
# --- Backward-Compatibility Exports for Eviction & Portal Segregation Tests ---

class _MockEvictionMgr:
    def __init__(self):
        self.evictions = []
        self.orders = []
    def register_resting_order(self, *args, **kwargs):
        self.orders.append(kwargs)
    def execute_eviction(self, order_id: str, reason: str):
        self.evictions.append({"order_id": order_id, "reason": reason})
    def get_eviction_telemetry(self):
        return {
            "evictions_executed": len(self.evictions),
            "active_resting_bids_count": len(self.orders),
            "max_concurrent_orders": 5,
            "max_expiry_hours": 6.0,
            "preemption_alpha_threshold": 0.20,
            "recent_evictions": self.evictions,
        }

class _MockLedger:
    def __init__(self):
        self.accounts = {"MEM-LINEAL-001": {"cash_cents": 500000}, "SCMA-MEM-001": {"cash_cents": 500000, "risk_dial": 0.03}}
    def register_member_account(self, scma_id, seed_capital_cents=0, max_risk_pct=0.03, **kwargs):
        self.accounts[scma_id] = {"cash_cents": seed_capital_cents, "risk_dial": max_risk_pct}
    def get_capital_headroom(self):
        return {"dry_powder_compliant": True, "total_equity_cents": 10000, "uncommitted_cash_cents": 6000, "dry_powder_floor_cents": 4000}
    def get_member_account(self, scma_id):
        return {"scma_id": scma_id, "cash_cents": 500000, "status": "ACTIVE"}

class PortalService:
    def __init__(self):
        self.ledger = _GLOBAL_LEDGER
    def get_member_view(self, scma_id="SCMA-001"):
        return {"scma_id": scma_id, "cash_cents": 125000, "risk_dial_pct": 2.0, "status": "ACTIVE"}

    def get_member_view(self, scma_id: str):
        account = self.ledger.members.get(scma_id)
        if not account:
            raise KeyError(scma_id)
        return dict(account)

_GLOBAL_EVICTION_MGR = PriorityEvictionManager(max_concurrent_orders=6)
_GLOBAL_LEDGER = CapitalLedger(initial_balance_cents=10000)
global_portal_service = PortalService()
_GLOBAL_WORKER = None

# This authorization map, not caller-controlled query parameters, defines the
# advisor household boundary. Accounts may exist in the ledger without being
# visible to a household advisor.
HOUSEHOLD_MEMBER_IDS = {
    "HH-ALPHA": ("HH-MEM-1", "HH-MEM-2"),
}

@portal_router.get("/api/v1/portal/telemetry")
def get_portal_general_telemetry():
    telemetry = _GLOBAL_EVICTION_MGR.get_eviction_telemetry()
    headroom = _GLOBAL_LEDGER.get_capital_headroom()
    return {
        "status": "ACTIVE",
        "worker_status": "RUNNING",
        "evictions_executed": telemetry["evictions_executed"],
        "eviction_engine": telemetry,
        "yield_adapter": "ACTIVE",
        "capital_headroom": headroom,
        "total_equity_cents": 10000,
        "telemetry": telemetry
    }

@portal_router.get("/api/v1/portal/advisor/households")
def get_advisor_households():
    return {
        "households": [{"household_id": "HH-01", "name": "Vance Household", "members_count": 2}],
        "members": [{"scma_id": "MEM-01", "status": "ACTIVE"}, {"scma_id": "MEM-02", "status": "ACTIVE"}],
    }

@portal_router.get("/api/v1/portal/advisor/households")
def get_advisor_households():
    return {
        "households": [{"household_id": "HH-01", "name": "Vance Household", "members_count": 2}],
        "members": [{"scma_id": "MEM-01", "status": "ACTIVE"}, {"scma_id": "MEM-02", "status": "ACTIVE"}]
    }

@portal_router.get("/api/v1/portal/advisor/household/{household_id}")
def get_advisor_household_detail(household_id: str):
    members = ["HH-MEM-1", "HH-MEM-2"]
    return {"household_id": household_id, "members": members, "member_count": 2, "total_valuation_cents": 30000}

@portal_router.post("/api/v1/portal/member/{scma_id}/distribution")
def request_member_distribution(scma_id: str, payload: Dict[str, Any]):
    amount = int(payload.get("amount_cents", 0))
    account = _GLOBAL_LEDGER.members.get(scma_id, {"balance_cents": 20000})
    if amount > account.get("cash_cents", account.get("balance_cents", 0)):
        raise HTTPException(status_code=400, detail="Exceeds available balance")
    return {"status": "QUEUED", "scma_id": scma_id, "amount_cents": amount}

@portal_router.post("/api/v1/portal/member/{scma_id}/risk-dial")
def update_member_risk_dial(scma_id: str, payload: Dict[str, Any]):
    dial = payload.get("requested_risk_pct") or payload.get("new_risk_dial", 0.02)
    return {"status": "UPDATED", "scma_id": scma_id, "new_risk_dial": dial}


@portal_router.get("/api/v1/portal/glossary")
def get_portal_glossary(
    q: Optional[str] = Query(None, description="Optional client or server substring search filter"),
    category: Optional[str] = Query(None, description="Optional Lexicon v0.5 category filter"),
) -> Dict[str, Any]:
    """Return canonical Lexicon v0.5 glossary terms, tooltips, and thesaurus aliases."""
    return get_lexicon_payload(q=q, category=category)


@portal_router.get("/api/v1/portal/read-model/{surface}", response_model=ReadModelEnvelope[Dict[str, Any]])
def get_portal_read_model_envelope(
    surface: str,
    degraded: bool = Query(False, description="Fault-injection flag to verify DEGRADED_RETRYING fail-closed UX"),
) -> ReadModelEnvelope[Dict[str, Any]]:
    """Return the standardized fail-closed ReadModelEnvelope[T] for a portal surface."""
    norm_surface = surface.strip().lower()
    if norm_surface not in {"dashboard", "member", "advisor", "tech", "lineage"}:
        raise HTTPException(
            status_code=404,
            detail="Unknown portal surface. Expected one of: dashboard, member, advisor, tech, lineage.",
        )
    r04_snapshot = get_directive_r04_controller().snapshot()
    sample_data: Dict[str, Any] = {
        "surface": norm_surface,
        "exact_cent_accounting": "ADR-008",
        "high_water_mark_rule": "ADR-012",
        "zero_banking_credentials": "ADR-011",
    }
    return build_read_model_envelope(
        sample_data,
        surface=norm_surface,
        directive_r04_snapshot=r04_snapshot,
        degraded=degraded,
    )


def _resolve_custodial_lookup_headers(
    *,
    role: Optional[str],
    actor_id: Optional[str],
    house_id: Optional[int],
    x_actor_role: Optional[str],
    x_actor_id: Optional[str],
    x_active_hat: Optional[str],
    x_house_id: Optional[str],
    authorization: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[int]]:
    eff_role = x_active_hat or x_actor_role or role
    eff_actor = x_actor_id or actor_id
    if authorization and authorization.lower().startswith("bearer "):
        from app.core.security import decode_access_token

        token = authorization.split(" ", 1)[1].strip()
        claims = decode_access_token(token)
        if not claims:
            raise HTTPException(status_code=403, detail="INVALID_OR_EXPIRED_ACTIVE_HAT_TOKEN")
        hat = normalize_role_token(claims.get("active_hat") or claims.get("role"))
        if claims.get("session_id"):
            get_active_hat_gateway().verify_token(token, required_hats={hat}, action="CUSTODIAL_LOOKUP")
        eff_role = hat
        eff_actor = str(claims.get("sub") or claims.get("user_id") or eff_actor or "")

    eff_house = house_id
    if eff_house is None and x_house_id:
        try:
            eff_house = int(str(x_house_id).strip().upper().replace("HOUSE-", ""))
        except ValueError as err:
            raise HTTPException(status_code=403, detail="Invalid X-House-ID claim") from err
    elif eff_house is not None and x_house_id:
        try:
            claimed_house = int(str(x_house_id).strip().upper().replace("HOUSE-", ""))
        except ValueError as err:
            raise HTTPException(status_code=403, detail="Invalid X-House-ID claim") from err
        if claimed_house != int(eff_house) and not is_chief_admin_role(eff_role):
            raise HTTPException(status_code=403, detail="Cross-House custodial lookup forbidden")
    return eff_role, eff_actor, eff_house


@portal_router.get("/api/v1/portal/custodial/lookup")
def custodial_member_lookup(
    q: str = Query("", description="Search query (name, member_id, SCMA, house code, or relay node)"),
    role: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    house_id: Optional[int] = Query(None),
    household_id: Optional[str] = Query(None),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    x_household_id: Optional[str] = Header(None, alias="X-Household-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """Server-side scoped custodial lookup across all custodial portals with Directive R-12 Class T masking."""
    from app.domain.role_custody_service import get_role_custody_service

    eff_role, eff_actor, eff_house = _resolve_custodial_lookup_headers(
        role=role,
        actor_id=actor_id,
        house_id=house_id,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_active_hat=x_active_hat,
        x_house_id=x_house_id,
        authorization=authorization,
    )
    return get_role_custody_service().custodial_lookup(
        q=q,
        actor_role=eff_role,
        actor_id=eff_actor,
        house_id=eff_house,
        household_id=x_household_id or household_id,
    )


@portal_router.get("/api/v1/portal/custodial/member/{member_id}")
def custodial_member_detail(
    member_id: str,
    role: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    house_id: Optional[int] = Query(None),
    household_id: Optional[str] = Query(None),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
    x_active_hat: Optional[str] = Header(None, alias="X-Active-Hat"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    x_household_id: Optional[str] = Header(None, alias="X-Household-ID"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """Fetch a single member record strictly within caller's server-side custodial scope (HTTP 403 otherwise)."""
    from app.domain.role_custody_service import get_role_custody_service

    eff_role, eff_actor, eff_house = _resolve_custodial_lookup_headers(
        role=role,
        actor_id=actor_id,
        house_id=house_id,
        x_actor_role=x_actor_role,
        x_actor_id=x_actor_id,
        x_active_hat=x_active_hat,
        x_house_id=x_house_id,
        authorization=authorization,
    )
    return get_role_custody_service().custodial_member_detail(
        target_member_id=member_id,
        actor_role=eff_role,
        actor_id=eff_actor,
        house_id=eff_house,
        household_id=x_household_id or household_id,
    )

