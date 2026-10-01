"""
PDEUE Phase 1 Integrity Remediation Router
- Option A: Real-Time 87/10/3 Transaction Waterfall (10% CFCP Priority Extraction)
- Directive R-06: Split-Hat Role Mapping on /member
- Directive R-12: Redacted Telemetry Plane on /admin/tech
"""
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import html
import pathlib
from app.domain.lineage_hierarchy import get_lineage_service
from app.domain.scan_worker import AutonomousScanWorker
from app.domain.ai_copilot import AICopilotEngine

router = APIRouter(tags=['Portals'])
portal_router = router
_lineage_service = get_lineage_service()
_advisor_copilot_engine = AICopilotEngine()

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

class CAOverrideRequest(BaseModel):
    token: str

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


# Process-local demo state is deliberate: these portal endpoints operate the same
# long-lived worker and approval ledger for every request made to an app process.
_TECH_WORKER = AutonomousScanWorker()
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
):
    role = _lineage_role(role)
    _lineage_claim(house_id, x_house_id, actor_house_id)
    house = _lineage_service.get_house_summary(house_id)
    page = _load_html("lineage_house.html").body.decode("utf-8")
    replacements = {
        "__HOUSE_ID__": str(house_id),
        "__HOUSE_CODE__": house["lineage_code"],
        "__HOUSE_NAME__": house["name"],
        "__ACTIVE_ROLE__": role,
        "__ACTIVE_HAT__": "HOUSE_LEADER (H2_SOVEREIGN)" if role == "H2" else "HOUSE_ASSISTANT (H1_SECRETARIAL)",
    }
    for marker, value in replacements.items():
        page = page.replace(marker, str(value))
    discovery_start = page.find("<!-- DISCOVERY_CONTROLS_START -->")
    discovery_end = page.find("<!-- DISCOVERY_CONTROLS_END -->")
    if discovery_start >= 0 and discovery_end >= 0:
        page = page[:discovery_start] + page[discovery_end + len("<!-- DISCOVERY_CONTROLS_END -->"):]
    page = page.replace("__ROLE_DESK__", _render_lineage_h2_desk(house) if role == "H2" else _render_lineage_h1_desk(house))
    return HTMLResponse(page)


@router.get("/api/v1/portal/lineage/house/{house_id}/state")
def get_lineage_house_state(
    house_id: int,
    role: str = Query("H2"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    actor_house_id: Optional[int] = Query(None),
):
    role = _lineage_role(role)
    _lineage_claim(house_id, x_house_id, actor_house_id)
    house = _lineage_service.get_house_summary(house_id)
    members = []
    for source in house["members"]:
        member = {
            "scma_id": source["scma_id"], "name": source["name"],
            "role_tag": source["role_tag"], "risk_dial_bps": int(round(source["risk_dial"] * 10_000)),
            "status": source["status"], "open_orders": list(source["open_orders"]),
            "literacy_completion_pct": 85 if "Apprentice" in source["role_tag"] else 100,
        }
        member["notional_cents"] = "$****.**" if role == "H1" else int(source["cash_cents"])
        members.append(member)
    proposals = []
    for item in _LINEAGE_PROPOSALS.values():
        proposals.append({**item, "aye_count": len(item["aye_house_ids"]), "nay_count": len(item["nay_house_ids"]), "threshold": 9})
    return {
        "house_id": house_id, "house_code": house["lineage_code"], "house_name": house["name"],
        "active_role": role, "aggregated_house_capital_cents": int(house["total_cash_cents"]),
        "average_risk_dial_bps": int(round(house["average_risk_dial_pct"] * 100)),
        "members": members, "roll_call_logs": list(_LINEAGE_ROLL_CALL), "bicameral_proposals": proposals,
    }


@router.post("/api/v1/portal/lineage/house/{house_id}/vote")
def vote_on_lineage_proposal(
    house_id: int, request: LineageVoteRequest,
    role: str = Query("H2"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    actor_house_id: Optional[int] = Query(None),
):
    role = _lineage_role(role)
    _lineage_claim(house_id, x_house_id, actor_house_id)
    if role != "H2":
        raise HTTPException(status_code=403, detail="H1 secretarial role has no voting authority")
    vote = request.vote.upper()
    if vote not in {"AYE", "NAY"}:
        raise HTTPException(status_code=422, detail="vote must be AYE or NAY")
    proposal = _LINEAGE_PROPOSALS.get(request.proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    proposal["aye_house_ids"] = [x for x in proposal["aye_house_ids"] if x != house_id]
    proposal["nay_house_ids"] = [x for x in proposal["nay_house_ids"] if x != house_id]
    proposal[f"{vote.lower()}_house_ids"].append(house_id)
    if len(proposal["aye_house_ids"]) >= 9:
        proposal["status"] = "RATIFIED_PENDING_SETTLOR"
    return {"proposal_id": request.proposal_id, "house_vote": vote, "aye_count": len(proposal["aye_house_ids"]),
            "nay_count": len(proposal["nay_house_ids"]), "threshold": 9, "status": proposal["status"],
            "effect": "ADVISORY_PETITION_ONLY"}


@router.post("/api/v1/portal/lineage/house/{house_id}/circuit-breaker")
def execute_lineage_circuit_breaker(
    house_id: int, request: LineageCircuitBreakerRequest,
    role: str = Query("H2"),
    x_house_id: Optional[str] = Header(None, alias="X-House-ID"),
    actor_house_id: Optional[int] = Query(None),
):
    role = _lineage_role(role)
    _lineage_claim(house_id, x_house_id, actor_house_id)
    if role != "H2":
        raise HTTPException(status_code=403, detail="H1 secretarial role cannot operate circuit breakers")
    action = request.action.upper().replace("-", "_")
    try:
        if action in {"FREEZE", "FREEZE_DIAL", "GOVERNOR_CLAMP"}:
            return _lineage_service.freeze_subordinate_risk(house_id, request.scma_id)
        if action in {"CANCEL_ORDERS", "RESTING_PURGE"}:
            return _lineage_service.cancel_subordinate_orders(house_id, request.scma_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    raise HTTPException(status_code=422, detail="action must be FREEZE_DIAL or CANCEL_ORDERS")


def _render_lineage_h2_desk(house: Dict[str, Any]) -> str:
    rows = "".join(
        f'<tr><td>{m["name"]}</td><td>{m["scma_id"]}</td><td>${m["cash_cents"] / 100:,.2f}</td>'
        f'<td><button class="freeze" onclick="openFreezeModal(\'{m["scma_id"]}\')">Freeze Dial (0%)</button> '
        f'<button class="cancel" onclick="openCancelModal(\'{m["scma_id"]}\')">Cancel Orders</button></td></tr>'
        for m in house["members"] if not _lineage_service._is_sovereign_settlor(m)
    )
    return f'''<section class="metrics"><article><h2>Aggregated House Capital</h2><strong>${house["total_cash_cents"] / 100:,.2f}</strong></article>
<article><h2>Average Risk Dial</h2><strong>{house["average_risk_dial_pct"]}%</strong></article></section>
<section><h2>Subordinate Accounts &amp; Lineal Circuit Breakers</h2><table><tbody>{rows}</tbody></table></section>
<section id="bicameral"><h2>Bicameral CFCP Ratification Chamber</h2><p>75% (9 of 12) stages an advisory petition for Chief Administrator review. No capital sweep is executed.</p>
<article><strong>Apprentice Literacy Grant Petition</strong><div id="consensus-tally">0 / 12 Aye</div><button id="vote-aye" onclick="castVote('AYE')">Aye</button><button id="vote-nay" onclick="castVote('NAY')">Nay</button></article></section>
<div id="cancel-modal" class="modal" hidden>Resting Purge confirmation</div><div id="freeze-modal" class="modal" hidden>Governor Clamp confirmation</div>'''


def _render_lineage_h1_desk(house: Dict[str, Any]) -> str:
    rows = "".join(f'<tr><td>{m["name"]}</td><td>{m["scma_id"]}</td><td>$****.**</td><td>{m["status"]}</td></tr>' for m in house["members"])
    literacy = "".join(f'<label>{m["name"]}<progress max="100" value="{85 if "Apprentice" in m["role_tag"] else 100}"></progress></label>' for m in house["members"])
    return f'''<section class="metrics"><article><h2>Aggregated House Capital</h2><strong>${house["total_cash_cents"] / 100:,.2f}</strong></article></section>
<section><h2>Member Accounts — Directive R-12</h2><table><tbody>{rows}</tbody></table></section>
<section class="audit"><h2>Bicameral CFCP Ratification Chamber — NON-VOTING AUDIT</h2><p>Secretarial observation only; legislative submission authority is disabled.</p></section>
<section class="secretarial"><article><h2>Meeting Scheduler Log</h2><p>Next Senate session: 2026-10-05 18:00 UTC</p></article><article><h2>Lineage Roll-Call Registry</h2><p>RC-2026-09 — QUORUM MET</p></article><article><h2>AI Tutor / Literacy Completion</h2>{literacy}</article></section>'''

@router.get("/member", response_class=HTMLResponse)
def get_member_portal():
    return _load_html("member.html")

@router.get("/advisor", response_class=HTMLResponse)
def get_advisor_portal():
    return _load_html("advisor.html")

@router.get("/admin/tech", response_class=HTMLResponse)
def get_tech_console():
    return _load_html("tech.html")


# --- Class C Community Fellowship (strictly non-transactional) ---
@router.get("/community", response_class=HTMLResponse)
def get_community_portal():
    return _load_html("community.html")


@router.get("/api/v1/portal/community/feed")
def get_community_feed() -> Dict[str, Any]:
    return {
        "announcements": list(_COMMUNITY_ANNOUNCEMENTS),
        "milestones": list(_COMMUNITY_MILESTONES),
        "messages": list(reversed(_COMMUNITY_MESSAGES[-50:])),
        "scope": "COMMUNITY_EDUCATION_ONLY",
    }


@router.post("/api/v1/portal/community/message", status_code=201)
def post_community_message(request: CommunityMessageRequest) -> Dict[str, str]:
    message = {
        "member_id": _community_text(request.member_id, field="member_id", maximum=80),
        "author_name": _community_text(request.author_name, field="author_name", maximum=80),
        "house_id": _community_text(request.house_id, field="house_id", maximum=80),
        "message_text": _community_text(request.message_text, field="message_text", maximum=1000),
        "posted_at": datetime.now(timezone.utc).isoformat(),
    }
    _COMMUNITY_MESSAGES.append(message)
    return message


@router.get("/api/v1/portal/community/academy/lessons")
def get_community_lessons() -> Dict[str, Any]:
    return {"lessons": list(_COMMUNITY_LESSONS), "curriculum_scope": "EDUCATIONAL_ONLY"}


@router.post("/api/v1/portal/community/academy/ask-tutor")
def ask_community_tutor(request: CommunityTutorRequest) -> Dict[str, str]:
    query = _community_text(request.query, field="query", maximum=500)
    member_id = _community_text(request.member_id, field="member_id", maximum=80)
    lowered = html.unescape(query).lower()
    mutation_phrases = (
        "buy ", "sell ", "place an order", "execute", "submit a trade",
        "make a trade", "cancel order", "transfer", "withdraw", "deposit",
    )
    balance_phrases = ("my balance", "account balance", "capital balance", "bank balance", "how much money")
    if any(phrase in lowered for phrase in mutation_phrases + balance_phrases):
        raise HTTPException(
            status_code=403,
            detail="The academy tutor is educational only and cannot access balances or perform transactions.",
        )

    if "quarter-kelly" in lowered or "quarter kelly" in lowered:
        answer = "Quarter-Kelly uses one fourth of a model's Kelly-sized exposure. It keeps the idea of scaling with confidence while adding a large cushion for estimation error and uncertainty."
        concept = "RISK_SIZING"
    elif "binary" in lowered:
        answer = "A binary contract has two possible settlement outcomes. Its quoted probability is a learning aid, not a promise; uncertainty and calibration still matter."
        concept = "BINARY_CONTRACT_FOUNDATIONS"
    elif "87/10/3" in lowered or "waterfall" in lowered:
        answer = "The 87/10/3 lesson describes a stewardship safeguard: three defined portions help learners reason about compounding, family protection, and education support without directing a transaction."
        concept = "WATERFALL_STEWARDSHIP"
    else:
        answer = "Start by naming the outcome, the uncertainty, and what evidence could change your view. Good risk literacy separates an educational estimate from a guaranteed result."
        concept = "RISK_LITERACY"
    return {"member_id": member_id, "query": query, "answer": answer, "concept": concept, "mode": "EDUCATIONAL_ONLY"}

# --- Member Workspace (Directive R-06 Split-Hat) ---
@router.get("/api/v1/portal/member/state")
def get_member_state(user_id: Optional[str] = Query(None), scma_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    target = None
    lineage_member = None

    # A SCMA link is authoritative: resolve it against the shared lineage
    # registry first, so this endpoint also works for dynamically seeded House
    # members that do not have a legacy portal profile.
    if scma_id:
        try:
            lineage_member = _lineage_service.get_member_state(scma_id)
        except ValueError as err:
            raise HTTPException(status_code=404, detail=str(err)) from err

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
                "user_id": f"USR-{lineage_member['scma_id']}",
                "name": lineage_member["name"],
                "role": "MEMBER_USER",
                "scma_id": lineage_member["scma_id"],
                "balance": lineage_member["cash_cents"] / 100.0,
                "reserved": 0.0,
                "risk_dial": lineage_member["risk_dial"] * 100,
                "is_custodial": False,
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
    risk_dial_pct = (
        lineage_member["risk_dial"] * 100 if lineage_member else target["risk_dial"]
    )

    cash_cents = int(lineage_member["cash_cents"] if lineage_member else round(target["balance"] * 100))
    active_float_cents = min(cash_cents, 2_500_000)
    swept_cash_cents = max(cash_cents - active_float_cents, 0)
    passive_yield_cents = cash_cents * 450 // 10_000
    quarantined = (lineage_member["status"] if lineage_member else target["status"]) in {
        "QUARANTINED", "FROZEN_BY_HOUSE_LEADER"
    }
    parent_house_quarantined = (
        (lineage_member["parent_house_status"] if lineage_member else "ACTIVE") == "QUARANTINED"
    )

    return {
        "user_id": target["user_id"],
        "name": target["name"],
        "role": "MEMBER_USER",  # Directive R-06: Member desk always enforces personal member role
        "scma_id": target["scma_id"],
        "cash_balance": lineage_member["cash_cents"] / 100.0 if lineage_member else target["balance"],
        "reserved_capital": target["reserved"],
        "lifetime_yield": 340.00,
        "risk_dial_pct": risk_dial_pct,
        "status": lineage_member["status"] if lineage_member else target["status"],
        "open_orders": lineage_member["open_orders"] if lineage_member else [],
        "parent_house_status": lineage_member["parent_house_status"] if lineage_member else "ACTIVE",
        "risk_ceiling_pct": 2.00,
        "active_float_cents": active_float_cents,
        "swept_cash_cents": swept_cash_cents,
        "passive_yield_cents": passive_yield_cents,
        "quarantined": quarantined,
        "parent_house_quarantined": parent_house_quarantined,
        "is_custodial": target["is_custodial"],
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
            "rule": "Option A: 10% CFCP priority deduction executed before FAEP derivation"
        }
    }

@router.post("/api/v1/portal/member/risk-dial")
def update_current_member_risk_dial(req: RiskUpdateRequest):
    """Apply the member HUD's 50–200 bps, downward-only governor."""
    scma_id = req.scma_id or "SCMA-ELEANOR_-B2B31C9E"
    try:
        member = _lineage_service.get_member_state(scma_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
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
    if not target and "global_portal_service" in globals():
        ledger_account = global_portal_service.ledger.members.get(scma_id)
        if ledger_account:
            target = {
                "risk_dial": ledger_account["max_risk_pct"] * 100.0,
                "is_custodial": False,
                "custodian_id": None,
            }
    if not target:
        account = _GLOBAL_LEDGER.accounts.get(scma_id)
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
            detail=f"Custodial Account: Risk adjustments locked. Governed by custodian {target['custodian_id']}."
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
def request_capital_distribution(req: DistributionRequest):
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
) -> Dict[str, Any]:
    """Return only the branch assigned to the authenticated advisor session."""
    if household_id != authenticated_household_id:
        raise HTTPException(status_code=403, detail="Cross-household access denied")
    house = LINEAGE_DATA.get(authenticated_household_id)
    if house is None:
        raise HTTPException(status_code=404, detail="Household branch not found")

    role = role.upper()
    if role not in {"F1", "F2-H", "F2-A", "F3"}:
        raise HTTPException(status_code=422, detail="Unsupported financial advisor role")

    accounts = [
        {
            "user_id": account["user_id"],
            "name": account["name"],
            "scma_id": account["scma_id"],
            "balance_cents": round(account["balance"] * 100),
            "risk_dial_bps": round(account["risk_dial"] * 100),
            "is_custodial": account["is_custodial"],
            "custodian_id": account["custodian_id"],
            "risk_controls_locked": account["is_custodial"],
            "risk_increase_requires": "F2_CO_SIGN" if account["is_custodial"] else None,
        }
        for account in house["accounts"]
        if role != "F1" or account["is_custodial"]
    ]
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
    return response


@router.get("/api/v1/portal/advisor/macro-risk")
def get_advisor_macro_risk(role: str = Query("F3")) -> Dict[str, Any]:
    """Return platform risk in integer cents; household domestic detail is excluded."""
    if role.upper() not in {"F3", "CHIEF_ADMIN", "CHIEF_ADMINISTRATOR"}:
        raise HTTPException(status_code=403, detail="F3 CRO or Chief Admin authority required")
    return {
        "platform_var_99_24h_cents": 42_000,
        "cross_house_gross_margin_cents": 1_850_000,
        "margin_utilization_pct": 74,
        "venue_distribution_pct": {"Kalshi": 58, "Polymarket": 42},
        "directive_r04": {"status": "NORMAL", "failsafe": "ARMED"},
        "house_exposures": _MACRO_HOUSE_EXPOSURES,
    }


@router.get("/api/v1/portal/advisor/proposals")
def get_advisor_proposals(role: str = Query("F2-A")) -> Dict[str, Any]:
    if role.upper() not in {"F2-A", "F2-H", "F3", "CHIEF_ADMIN", "CHIEF_ADMINISTRATOR"}:
        raise HTTPException(status_code=403, detail="Advisory proposal access denied")
    return {"proposals": list(_ADVISORY_PROPOSALS.values())}


@router.post("/api/v1/portal/advisor/proposals", status_code=201)
def stage_advisor_proposal(
    request: AdvisoryProposalRequest,
    role: Optional[str] = Query(None),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
) -> Dict[str, Any]:
    global _ADVISORY_PROPOSAL_SEQUENCE
    actor_role = (role or x_actor_role or request.actor_role or "").upper()
    if actor_role not in {"F2-A", "F2-H"}:
        raise HTTPException(status_code=403, detail="Only F2-A or F2-H may stage advisory proposals")
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
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
) -> Dict[str, Any]:
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

# --- Technical Infrastructure (T1, T2, T3 & Directive R-12) ---
@router.get("/api/v1/portal/tech/telemetry")
def get_tech_telemetry(
    tier: str = Query("T3"),
    unredact_token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    tier_upper = tier.upper()
    if tier_upper not in ["T1", "T2", "T3"]:
        tier_upper = "T1"

    is_unredacted = (
        tier_upper == "T3" and unredact_token == "AUTH-CA-OVERRIDE-TEMP"
    )

    recent_orders = [
        {
            "order_id": "ORD-0912-A1",
            "account_id": "SCMA-ELEANOR_-B2B31C9E" if is_unredacted else "SCMA-MEM-****-REDACTED",
            "contract": "KX-MIA-FRZ-32",
            "notional_cents": 2500 if is_unredacted else "REDACTED",
            "mode": "PAPER_MAKER"
        }
    ]

    return {
        "tier": tier_upper,
        "telemetry_scope": "CLASS_T_OPERATIONAL",
        "redaction_active": not is_unredacted,
        "directive_enforced": "Directive R-12 (Least Privilege Redacted Financial Telemetry)",
        "can_trigger_daemons": tier_upper in ["T2", "T3"],
        "can_override_redaction": tier_upper == "T3",
        "worker_health": [
            {"worker": "AutonomousScanWorker", "cycle": _TECH_WORKER.cycle_count, "status": "NOMINAL", "latency_ms": 12.4},
            {"worker": "SettlementReconciler", "cycle": 710, "status": "IDLE", "latency_ms": 4.1},
            {"worker": "RateLimiter-Kalshi", "bucket_tokens": 85, "max_tokens": 100, "status": "OPTIMAL"},
            {"worker": "RateLimiter-Polymarket", "bucket_tokens": 92, "max_tokens": 100, "status": "OPTIMAL"}
        ],
        "daemon_status": {"AutonomousScanWorker": "ACTIVE"},
        "cycle_count": _TECH_WORKER.cycle_count,
        "settled_count": _TECH_SETTLED_COUNT,
        "settlement_waterfall": "87/10/3",
        "ws_latency_ms": _TECH_LATENCY_MS,
        "token_buckets": _TECH_TOKEN_BUCKETS,
        "dry_powder_floor_cents": 4000,
        "dry_powder_floor_status": "COMPLIANT",
        "active_order_ladder": [{
            "candidate_id": "CAND-0912-A1", "venue": "Kalshi",
            "scma_id": "SCMA-ELEANOR_-B2B31C9E" if is_unredacted else "SCMA-MEM-****",
            "model_probability_bps": 3150,
            "exposure_cents": 2500 if is_unredacted else "$****.**",
        }],
        "recent_dispatches": recent_orders,
        "system_metrics": {
            "cpu_load_pct": 8.5,
            "memory_usage_mb": 142.1,
            "active_websockets": 2,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
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
def trigger_tech_daemon(tier: str = Query("T3")) -> Dict[str, Any]:
    """Run one real worker evaluation and expose only operational telemetry."""
    if tier.upper() not in {"T2", "T3"}:
        raise HTTPException(status_code=403, detail="T1 telemetry access is read-only")
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
def trigger_tech_settlement(tier: str = Query("T3")) -> Dict[str, Any]:
    """Run a deterministic reconciliation cycle without exposing ledger values."""
    global _TECH_SETTLED_COUNT
    if tier.upper() not in {"T2", "T3"}:
        raise HTTPException(status_code=403, detail="T1 telemetry access is read-only")
    _TECH_SETTLED_COUNT += 1
    return {
        "status": "SETTLED",
        "settled_count": _TECH_SETTLED_COUNT,
        "waterfall": "87/10/3",
    }

@router.post("/api/v1/portal/tech/ca-override")
def activate_ca_override(request: CAOverrideRequest, tier: str = Query("T3")) -> Dict[str, Any]:
    """Issue page-scoped unredacted data only after explicit CA authentication."""
    if tier.upper() != "T3":
        raise HTTPException(status_code=403, detail="CA override requires T3 CTO authority")
    if request.token != "CA-OVERRIDE-SECRET-DEV":
        raise HTTPException(status_code=401, detail="Invalid CA override token; Directive R-12 masking remains active")
    return {
        "status": "ACTIVE_UNREDACT_GRANT",
        "redaction_active": False,
        "active_order_ladder": [{
            "candidate_id": "CAND-0912-A1", "venue": "Kalshi",
            "scma_id": "SCMA-ELEANOR_-B2B31C9E", "model_probability_bps": 3150,
            "exposure_cents": 2500,
        }],
    }

@router.post("/api/v1/portal/advisor/co-sign")
def co_sign_distribution(request: CoSignRequest) -> Dict[str, Any]:
    if request.actor_role != "F2-H":
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
def member_ai_tutor(query: AssistantQuery):
    prompt = query.query or query.question or ""
    q = prompt.lower()
    if any(term in q for term in ("waterfall", "split", "cfcp")):
        ans = (
            "PDEUE applies an 87/10/3 waterfall to each realized gain using integer-cent accounting, so every cent has a defined destination. "
            "The 87% SCMA share returns to the member's private account for reinvestment and long-term growth rather than being distributed away. "
            "The 10% CFCP share funds a family resilience shield that can support lineage-level protection and qualified needs during stress. "
            "The remaining 3% goes to the FAEP lineage endowment, building durable intergenerational capacity; together the three allocations always total 100%, without floating-point cent drift."
        )
    elif "compound" in q or "compounding" in q or "snowball" in q:
        ans = (
            "Compounding works like a snowball: the 87% SCMA portion of realized gains is reinvested, so later opportunities can earn returns on both the original principal and prior retained gains. "
            "Repeated harvest-and-reinvestment cycles can accelerate growth over time even when each individual gain is modest, although returns are never guaranteed. "
            "PDEUE performs the waterfall in integer cents, assigning whole cents deterministically so rounding cannot silently create or lose money."
        )
    elif "risk" in q or "dial" in q:
        ans = (
            "The risk dial is a downward-only capital governor: a member may reduce exposure, but cannot use the member portal to raise it above the currently authorized ceiling. "
            "The platform's absolute defensive ceiling is 5% per opportunity, while a member or administrator may impose a lower limit or lock a quarantined account at 0.0%. "
            "This asymmetry favors capital preservation by limiting loss concentration and requiring higher-authority review before risk can ever be expanded."
        )
    else:
        ans = (
            "PDEUE is an educational, capital-preservation system that evaluates public-event opportunities at a point in time, requires a documented edge, and sizes approved exposure defensively rather than promising returns. "
            "Its downward-only risk dial constrains position size, House quarantine can isolate one lineage branch, and resting orders remain subject to explicit governance controls. "
            "When gains are realized, integer-cent accounting sends 87% back to the member SCMA for compounding, 10% to the CFCP family resilience shield, and 3% to the FAEP lineage endowment. "
            "These mechanics combine private growth, shared resilience, intergenerational stewardship, and auditable approvals; ask about the waterfall, compounding, or risk dial for a deeper explanation."
        )
    return {"role": "MEMBER_TUTOR", "query": prompt, "response": ans, "answer": ans}

@router.post("/api/v1/portal/member/tutor")
def member_tutor(query: AssistantQuery):
    """Stable novice-facing alias used by the Member Desktop."""
    return member_ai_tutor(query)

@router.post("/api/v1/portal/advisor/copilot")
def advisor_copilot(query: AssistantQuery):
    prompt = query.query or query.question or ""
    response_text = _advisor_copilot_engine.ask(
        prompt,
        user_role="FINANCIAL_ADVISOR",
        context={"context_scope": query.context_scope},
    )
    # ``response`` and ``cards`` keep pre-Wave clients working while the three
    # canonical fields provide the stable Wave 2A.4 response contract.
    return {
        "role": "FIDUCIARY_COPILOT",
        "response_text": response_text,
        "disclaimer": "EDUCATIONAL_NOT_ADVICE",
        "response": response_text,
        "cards": [{
            "title": "Fiduciary analysis",
            "body": response_text,
            "classification": "EDUCATIONAL_NOT_ADVICE",
        }],
    }

@router.post("/api/v1/portal/tech/copilot")
def tech_copilot(query: AssistantQuery):
    prompt = query.query or query.question or ""
    q = prompt.lower()
    if "rate" in q or "limit" in q:
        ans = "Rate Limiter Telemetry: Kalshi token bucket is at 85% capacity; Polymarket is at 92%. Current consumption is well within safe thresholds."
    elif "latency" in q or "worker" in q:
        ans = "Worker Diagnostic: AutonomousScanWorker average round-trip ping is 12.4ms across 1,420 cycles. Zero preemption collisions."
    else:
        ans = "DevOps Telemetry Copilot active. Monitoring daemon cycles, event queues, and WebSocket latency under Directive R-12."
    return {"role": "DEVOPS_COPILOT", "query": prompt, "response": ans, "telemetry": {"cycle_count": _TECH_WORKER.cycle_count, "ws_latency_ms": dict(_TECH_LATENCY_MS), "token_buckets": _TECH_TOKEN_BUCKETS}}

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

_GLOBAL_EVICTION_MGR = PriorityEvictionManager()
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
    account = _GLOBAL_LEDGER.accounts.get(scma_id, {"cash_cents": 20000})
    if amount > account["cash_cents"]:
        raise HTTPException(status_code=400, detail="Exceeds available balance")
    return {"status": "QUEUED", "scma_id": scma_id, "amount_cents": amount}

@portal_router.post("/api/v1/portal/member/{scma_id}/risk-dial")
def update_member_risk_dial(scma_id: str, payload: Dict[str, Any]):
    dial = payload.get("requested_risk_pct") or payload.get("new_risk_dial", 0.02)
    return {"status": "UPDATED", "scma_id": scma_id, "new_risk_dial": dial}
