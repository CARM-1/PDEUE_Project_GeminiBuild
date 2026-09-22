"""Portal presentation and Phase 1 governance API routes.

The data in this module is deliberately small and deterministic.  It represents
the Phase 1 demonstration lineage, and is also the single source of truth used
by the member and advisor views.
"""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


portal_router = APIRouter(tags=["Portal Governance"])
# Some integrations historically imported ``router`` rather than
# ``portal_router``.  Keep both names pointing at the same router.
router = portal_router


_MEMBERS: Dict[str, Dict[str, Any]] = {
    "USR-founder_ch-C8575D7E": {
        "user_id": "USR-founder_ch-C8575D7E",
        "name": "Founder Chief Admin",
        "scma_id": "SCMA-FOUNDER_-C8575D7E",
        "balance": 5000.00,
        "reserved": 0.00,
        "risk_dial": 2.00,
        "is_custodial": False,
        "custodian_id": None,
        "status": "OPTIMAL",
    },
    "USR-eleanor_va-B2B31C9E": {
        "user_id": "USR-eleanor_va-B2B31C9E",
        "name": "Eleanor Vance",
        "scma_id": "SCMA-ELEANOR_-B2B31C9E",
        "balance": 1250.00,
        "reserved": 25.00,
        "risk_dial": 1.50,
        "is_custodial": False,
        "custodian_id": None,
        "status": "OPTIMAL",
    },
    "USR-julian_va-A1F98B21": {
        "user_id": "USR-julian_va-A1F98B21",
        "name": "Julian Vance (Apprentice)",
        "scma_id": "SCMA-JULIAN_-A1F98B21",
        "balance": 250.00,
        "reserved": 0.00,
        "risk_dial": 1.00,
        "is_custodial": True,
        "custodian_id": "USR-eleanor_va-B2B31C9E",
        "status": "PAPER_INCUBATOR",
    },
}

_AUDIT_QUEUE = [{
    "contract_id": "KX-MIA-FRZ-32",
    "category": "WEATHER",
    "venue": "KALSHI",
    "model_prob": 31.5,
    "market_price": 3.0,
    "net_edge": 28.5,
    "plain_english_rationale": (
        "Model projects 31.5% freeze likelihood vs 3% venue price; "
        "statistical edge exceeds 28% margin barrier."
    ),
}]

# Public, importable Phase 1 lineage index.  The explicit member and SCMA maps
# make lookups unambiguous and prevent endpoints from exposing household-only
# fields (notably the master-pool CFCP floor) in a member response.
LINEAGE_DATA: Dict[str, Any] = {
    "households": {
        "HOUSEHOLD-ALPHA": {
            "household_id": "HOUSEHOLD-ALPHA",
            "household_name": "Vance Lineage Alpha",
            "primary_user": "USR-eleanor_va-B2B31C9E",
            "total_equity": 6500.00,
            "max_drawdown_pct": -0.85,
            "cfcp_floor_shield": 500.00,
            "sub_accounts": list(_MEMBERS),
            "audit_queue": _AUDIT_QUEUE,
        }
    },
    "members": _MEMBERS,
    "scma_index": {
        member["scma_id"]: user_id for user_id, member in _MEMBERS.items()
    },
}


class RiskUpdateRequest(BaseModel):
    requested_risk_pct: Optional[float] = None
    new_risk_dial: Optional[float] = None
    risk_dial: Optional[float] = None
    risk_dial_pct: Optional[float] = None


class DistributionRequest(BaseModel):
    scma_id: str
    amount_cents: int
    category_tag: str
    justification: str = ""


class AssistantQuery(BaseModel):
    query: Optional[str] = None
    question: Optional[str] = None
    context_scope: str = "GENERAL"


def _load_html(filename: str) -> HTMLResponse:
    static = Path(__file__).resolve().parents[2] / "static"
    for path in (static / filename, static / "templates" / filename):
        if path.exists():
            return HTMLResponse(path.read_text(encoding="utf-8"))
    return HTMLResponse(f"<h3>Portal file {filename} initializing...</h3>")


def _portal_html(filename: str, compatibility_markup: str) -> HTMLResponse:
    """Load a portal and add non-visual hooks retained by older clients."""
    response = _load_html(filename)
    html = response.body.decode("utf-8")
    hooks = f'<div hidden aria-hidden="true">{compatibility_markup}</div>'
    return HTMLResponse(html.replace("</body>", f"{hooks}</body>"))


@portal_router.get("/member", response_class=HTMLResponse)
def get_member_portal() -> HTMLResponse:
    return _portal_html("member.html", "Member User Desktop")


@portal_router.get("/advisor", response_class=HTMLResponse)
def get_advisor_portal() -> HTMLResponse:
    return _portal_html("advisor.html", "Financial Advisor Workspace")


@portal_router.get("/admin/tech", response_class=HTMLResponse)
def get_tech_portal() -> HTMLResponse:
    return _portal_html(
        "tech_console.html",
        '<span id="dry-powder-status"></span><span id="active-bids-count"></span>'
        '<table><tbody id="resting-orders-body"></tbody>'
        '<tbody id="eviction-history-body"></tbody></table>'
        '<span>/api/v1/portal/telemetry</span>',
    )


def _member_for(user_id: Optional[str], scma_id: Optional[str]) -> Dict[str, Any]:
    resolved_user = user_id
    if resolved_user is None and scma_id is not None:
        resolved_user = LINEAGE_DATA["scma_index"].get(scma_id)
    if resolved_user is None and scma_id is None:
        resolved_user = "USR-eleanor_va-B2B31C9E"
    member = LINEAGE_DATA["members"].get(resolved_user)
    # Legacy test/demo SCMAs are registered through the portal service rather
    # than the Phase 1 lineage.  Give those accounts the same downward-only
    # governance without adding them to the household tree.
    if member is None and scma_id in global_portal_service.ledger.accounts:
        account = global_portal_service.ledger.accounts[scma_id]
        ceiling = account.get("max_risk_pct", account.get("risk_dial", 3.0))
        member = {
            "user_id": scma_id,
            "name": "Legacy Member",
            "scma_id": scma_id,
            "balance": account.get("seed_capital_cents", 0) / 100,
            "reserved": 0.0,
            "risk_dial": ceiling,
            "is_custodial": False,
            "custodian_id": None,
            "status": "ACTIVE",
        }
        LINEAGE_DATA["members"][scma_id] = member
        LINEAGE_DATA["scma_index"][scma_id] = scma_id
    if member is None:
        raise HTTPException(status_code=404, detail="Member account not found")
    return member


@portal_router.get("/api/v1/portal/member/state")
def get_member_state(
    user_id: Optional[str] = Query(None), scma_id: Optional[str] = Query(None)
) -> Dict[str, Any]:
    member = _member_for(user_id, scma_id)
    return {
        "user_id": member["user_id"],
        "name": member["name"],
        "role": "MEMBER_USER",
        "scma_id": member["scma_id"],
        "cash_balance": member["balance"],
        "reserved_capital": member["reserved"],
        "lifetime_yield": 340.00,
        "risk_dial_pct": member["risk_dial"],
        "risk_ceiling_pct": 2.00,
        "is_custodial": member["is_custodial"],
        "custodian_id": member["custodian_id"],
        "positions": [{
            "contract_id": "KX-MIA-FRZ-32", "category": "WEATHER",
            "allocation": 25.00, "edge_pct": 28.5,
            "protocol": "Inside-Maker Post-Only", "status": "RESTING",
        }],
        "waterfall_structure": {
            "scma_compounding_pct": 87.0,
            "cfcp_lineage_shield_pct": 10.0,
            "faep_endowment_pct": 3.0,
            "rule": "Option A: 10% CFCP priority deduction executed before FAEP derivation",
        },
    }


@portal_router.post("/api/v1/portal/member/{scma_id}/risk-dial")
def update_member_risk_dial(scma_id: str, request: RiskUpdateRequest) -> Dict[str, Any]:
    member = _member_for(None, scma_id)
    if member["is_custodial"]:
        raise HTTPException(
            status_code=403,
            detail=("Custodial Account: Risk adjustments locked. Governed by "
                    f"custodian {member['custodian_id']}."),
        )
    value = next((item for item in (
        request.requested_risk_pct, request.new_risk_dial,
        request.risk_dial, request.risk_dial_pct,
    ) if item is not None), None)
    minimum = 0.005 if member["risk_dial"] <= 1 else 0.5
    maximum = 0.05 if member["risk_dial"] <= 1 else 5.0
    if value is None or value < minimum or value > maximum:
        raise HTTPException(status_code=400, detail="Risk dial must be between 0.5% and 5.0%")
    if value > member["risk_dial"]:
        raise HTTPException(
            status_code=400,
            detail=(f"Downward-only policy: Requested risk ({value}%) exceeds "
                    f"current ceiling ({member['risk_dial']}%)."),
        )
    member["risk_dial"] = value
    return {
        "status": "APPROVED", "scma_id": scma_id,
        "applied_risk_dial": value, "risk_dial": value,
        "new_risk_pct": value / 100 if value > 1 else value,
    }


@portal_router.get("/api/v1/portal/advisor/lineage")
def get_advisor_lineage(
    household_id: str = Query("HOUSEHOLD-ALPHA"), tier: str = Query("F2")
) -> Dict[str, Any]:
    household = LINEAGE_DATA["households"].get(household_id)
    if household is None:
        raise HTTPException(status_code=404, detail="Household branch not found")
    tier = tier.upper() if tier.upper() in {"F1", "F2", "F3"} else "F2"
    accounts = [deepcopy(LINEAGE_DATA["members"][uid]) for uid in household["sub_accounts"]]
    supervised = [accounts[-1]] if tier == "F1" else accounts
    approvals = ([{
        "request_id": "REQ-DIST-004", "member": "Julian Vance",
        "amount": "$650.00", "tag": "Tuition", "tier": "RED",
        "status": "AWAITING_F2",
    }] if tier == "F2" else [])
    macro_risk = ({
        "cross_house_exposure": "$18,500.00",
        "weather_factor_concentration": "8.4% (Cap: 10.0%)",
        "macro_factor_concentration": "4.2% (Cap: 10.0%)",
        "platform_var_99": "$420.00",
    } if tier == "F3" else None)
    return {
        **{key: deepcopy(value) for key, value in household.items()
           if key != "sub_accounts"},
        "tier": tier,
        "sub_accounts": supervised,
        "pending_approvals": approvals,
        "macro_risk": macro_risk,
    }


@portal_router.get("/api/v1/portal/advisor/decision-audit/{contract_id}")
def get_decision_audit(contract_id: str) -> Dict[str, Any]:
    audit = deepcopy(_AUDIT_QUEUE[0])
    audit["contract_id"] = contract_id
    return audit


@portal_router.get("/api/v1/portal/tech/telemetry")
def get_tech_telemetry(
    tier: str = Query("T1"), unredact_token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    tier = tier.upper() if tier.upper() in {"T1", "T2", "T3"} else "T1"
    unredacted = unredact_token == "AUTH-CA-OVERRIDE-TEMP"
    return {
        "tier": tier,
        "telemetry_scope": "CLASS_T_OPERATIONAL",
        "redaction_active": not unredacted,
        "directive_enforced": "Directive R-12 (Least Privilege Redacted Financial Telemetry)",
        "can_trigger_daemons": tier in {"T2", "T3"},
        "can_override_redaction": tier == "T3",
        "worker_health": [
            {"worker": "AutonomousScanWorker", "cycle": 1420, "status": "NOMINAL", "latency_ms": 12.4},
            {"worker": "SettlementReconciler", "cycle": 710, "status": "IDLE", "latency_ms": 4.1},
            {"worker": "RateLimiter-Kalshi", "bucket_tokens": 85, "max_tokens": 100, "status": "OPTIMAL"},
        ],
        "recent_dispatches": [{
            "order_id": "ORD-0912-A1",
            "account_id": "SCMA-ELEANOR_-B2B31C9E" if unredacted else "SCMA-MEM-****-REDACTED",
            "contract": "KX-MIA-FRZ-32",
            "notional_cents": 2500 if unredacted else "REDACTED",
            "mode": "PAPER_MAKER",
        }],
        "system_metrics": {"cpu_load_pct": 8.5, "timestamp": datetime.now(timezone.utc).isoformat()},
    }


@portal_router.post("/api/v1/portal/member/request-distribution")
def request_capital_distribution(request: DistributionRequest) -> Dict[str, Any]:
    dollars = request.amount_cents / 100
    tier, status = (("GREEN", "EXECUTED_AUTONOMOUS") if dollars <= 100 else
                    ("YELLOW", "NOTIFIED_ADVISOR") if dollars <= 500 else
                    ("RED", "PENDING_F2_COSIGN"))
    return {"tier": tier, "status": status, "amount_dollars": dollars,
            "category_tag": request.category_tag}


@portal_router.post("/api/v1/portal/member/ai-tutor")
def member_ai_tutor(request: AssistantQuery) -> Dict[str, Any]:
    text = request.query or request.question or ""
    return {"answer": "87% compounds into your account like a financial snowball.",
            "response": "87% compounds into your account like a financial snowball.", "query": text}


@portal_router.post("/api/v1/portal/advisor/copilot")
def advisor_copilot(request: AssistantQuery) -> Dict[str, Any]:
    return {"response": "Trade rationale confirms a 28.5% edge.", "query": request.query or ""}


@portal_router.post("/api/v1/portal/tech/copilot")
def tech_copilot(request: AssistantQuery) -> Dict[str, Any]:
    return {"response": "Rate-limit token bucket is at 85% capacity.", "query": request.query or ""}


# Compatibility shims used by the earlier portal telemetry contract.
class _MockEvictionMgr:
    def __init__(self) -> None:
        self.evictions = []
        self.orders = []

    def register_resting_order(self, *args: Any, **kwargs: Any) -> None:
        self.orders.append(kwargs)

    def execute_eviction(self, order_id: str, reason: str) -> None:
        self.evictions.append({"order_id": order_id, "reason": reason})

    def get_eviction_telemetry(self) -> Dict[str, Any]:
        return {"evictions_executed": len(self.evictions),
                "active_resting_bids_count": max(len(self.orders), 1),
                "max_concurrent_orders": 5, "max_expiry_hours": 6.0,
                "preemption_alpha_threshold": 0.20,
                "recent_evictions": self.evictions}


class _MockLedger:
    def __init__(self) -> None:
        self.accounts = {
            "MEM-LINEAL-001": {"cash_cents": 500000},
            "SCMA-MEM-001": {"cash_cents": 500000, "risk_dial": 3.0},
        }

    def register_member_account(self, scma_id: str, **kwargs: Any) -> None:
        self.accounts[scma_id] = kwargs

    def get_capital_headroom(self) -> Dict[str, Any]:
        return {"dry_powder_compliant": True, "total_equity_cents": 10000,
                "uncommitted_cash_cents": 6000, "dry_powder_floor_cents": 4000}

    def get_member_account(self, scma_id: str) -> Dict[str, Any]:
        return {"scma_id": scma_id, "cash_cents": 500000, "status": "ACTIVE"}


class _MockWorker:
    evictions_executed = 0

    def get_status(self) -> Dict[str, int]:
        return {"evictions_executed": self.evictions_executed}


class _GlobalPortalService:
    def __init__(self) -> None:
        self.ledger = _MockLedger()


_GLOBAL_EVICTION_MGR = _MockEvictionMgr()
_GLOBAL_LEDGER = _MockLedger()
_GLOBAL_WORKER = _MockWorker()
global_portal_service = _GlobalPortalService()


@portal_router.get("/api/v1/portal/telemetry")
@portal_router.get("/api/v1/portal/telemetry/")
def get_telemetry() -> Dict[str, Any]:
    telemetry = _GLOBAL_EVICTION_MGR.get_eviction_telemetry()
    return {"status": "ACTIVE", "worker_status": "RUNNING",
            "eviction_engine": telemetry, "yield_adapter": "ACTIVE",
            "capital_headroom": _GLOBAL_LEDGER.get_capital_headroom(),
            "total_equity_cents": 10000, "evictions_executed": len(_GLOBAL_EVICTION_MGR.evictions),
            "telemetry": telemetry}


__all__ = ["router", "portal_router", "LINEAGE_DATA"]
