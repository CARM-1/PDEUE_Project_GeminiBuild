"""
PDEUE Phase 1 Comprehensive Portal Router
Enforces Tier-Adaptive Workspaces (F1-F3, T1-T3), Scoped Assistants,
Directive R-12 Redaction, and Three-Tier Distribution Gateway.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import pathlib

router = APIRouter(tags=['Portals'])
portal_router = router

LINEAGE_DATA: Dict[str, Any] = {
    "HOUSEHOLD-ALPHA": {
        "household_id": "HOUSEHOLD-ALPHA",
        "household_name": "Vance Lineage Alpha",
        "total_equity": 6500.00,
        "max_drawdown_pct": -0.85,
        "cfcp_floor_shield": 500.00,
        "accounts": [
            {
                "user_id": "USR-founder_ch-C8575D7E",
                "name": "Founder Chief Admin",
                "role": "CHIEF_ADMINISTRATOR",
                "scma_id": "SCMA-FOUNDER_-C8575D7E",
                "balance": 5000.00,
                "reserved": 0.00,
                "risk_dial": 2.00,
                "is_custodial": False,
                "custodian_id": None,
                "assigned_mentor": None,
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
                "assigned_mentor": None,
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
                "assigned_mentor": "USR-eleanor_va-B2B31C9E",
                "status": "PAPER_INCUBATOR"
            }
        ]
    }
}

class RiskUpdateRequest(BaseModel):
    requested_risk_pct: Optional[float] = None
    new_risk_dial: Optional[float] = None
    risk_dial: Optional[float] = None
    risk_dial_pct: Optional[float] = None

class DistributionRequest(BaseModel):
    scma_id: str
    amount_cents: int
    category_tag: str  # Tuition, Medical, Real Estate, Personal
    justification: Optional[str] = ""

class AssistantQuery(BaseModel):
    query: str
    context_scope: Optional[str] = "GENERAL"

def _load_html(filename: str) -> HTMLResponse:
    base = pathlib.Path(__file__).parent.parent.parent / "static"
    p1 = base / filename
    p2 = base / "templates" / filename
    if p1.exists():
        return HTMLResponse(content=p1.read_text(encoding="utf-8"))
    if p2.exists():
        return HTMLResponse(content=p2.read_text(encoding="utf-8"))
    return HTMLResponse(f"<h3>Portal file {filename} initializing...</h3>")

# --- HTML Visualizer Endpoints ---
@router.get("/member", response_class=HTMLResponse)
def get_member_portal():
    return _load_html("member.html")

@router.get("/advisor", response_class=HTMLResponse)
def get_advisor_portal():
    return _load_html("advisor.html")

@router.get("/admin/tech", response_class=HTMLResponse)
def get_tech_console():
    return _load_html("tech_console.html")

# --- Member Workspace Endpoints ---
@router.get("/api/v1/portal/member/state")
def get_member_state(user_id: Optional[str] = Query(None), scma_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    target = None
    for house in LINEAGE_DATA.values():
        for acct in house["accounts"]:
            if (user_id and acct["user_id"] == user_id) or (scma_id and acct["scma_id"] == scma_id):
                target = acct
                break
        if target:
            break
    if not target:
        target = LINEAGE_DATA["HOUSEHOLD-ALPHA"]["accounts"][1]

    return {
        "user_id": target["user_id"],
        "name": target["name"],
        "role": target["role"],
        "scma_id": target["scma_id"],
        "cash_balance": target["balance"],
        "reserved_capital": target["reserved"],
        "lifetime_yield": 340.00,
        "risk_dial_pct": target["risk_dial"],
        "risk_ceiling_pct": 2.00,
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
        "waterfall_structure": {"scma": 87.0, "cfcp": 10.0, "faep": 3.0}
    }

@router.post("/api/v1/portal/member/{scma_id}/risk-dial")
def update_member_risk_dial(scma_id: str, req: RiskUpdateRequest):
    target = None
    for house in LINEAGE_DATA.values():
        for acct in house["accounts"]:
            if acct["scma_id"] == scma_id or acct["user_id"] == scma_id:
                target = acct
                break
    if not target:
        raise HTTPException(status_code=404, detail="SCMA account not found")

    if target["is_custodial"]:
        raise HTTPException(
            status_code=403,
            detail=f"Custodial Account: Risk adjustments locked. Governed by custodian {target['custodian_id']}."
        )

    val = req.requested_risk_pct
    if val is None:
        raw = req.new_risk_dial if req.new_risk_dial is not None else (req.risk_dial if req.risk_dial is not None else req.risk_dial_pct)
        if raw is not None:
            val = raw if raw <= 5.0 else raw / 100.0

    if val is None or val < 0.5 or val > 5.0:
        raise HTTPException(status_code=400, detail="Risk dial must be between 0.5% and 5.0%")

    if val > target["risk_dial"]:
        raise HTTPException(
            status_code=400,
            detail=f"Downward-only policy: Requested risk ({val}%) exceeds current ceiling ({target['risk_dial']}%)."
        )

    target["risk_dial"] = val
    return {"status": "APPROVED", "scma_id": scma_id, "applied_risk_dial": val, "risk_dial": val}

@router.post("/api/v1/portal/member/request-distribution")
def request_capital_distribution(req: DistributionRequest):
    allowed_tags = ["Tuition", "Medical", "Real Estate", "Personal"]
    if req.category_tag not in allowed_tags:
        raise HTTPException(status_code=400, detail=f"Invalid tag. Must be one of {allowed_tags}")

    # Determine Tier: Green (< $100 profit sweep), Yellow ($100-$500), Red (> $500 or seed depletion)
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

# --- Advisor Workspace Endpoints (Tier-Aware: F1, F2, F3) ---
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

    # F1 Peer Guide: Scoped to 1 mentee
    if tier_upper == "F1":
        supervised = [house["accounts"][2]] # Julian Vance apprentice only
        approvals = []
        macro_risk = None
    elif tier_upper == "F2":
        supervised = house["accounts"]
        approvals = [
            {"request_id": "REQ-DIST-004", "member": "Julian Vance", "amount": "$650.00", "tag": "Tuition", "tier": "RED", "status": "AWAITING_F2"}
        ]
        macro_risk = None
    else:  # F3 Chief Risk Officer
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

# --- Technical Infrastructure Endpoints (Tier-Aware: T1, T2, T3) ---
@router.get("/api/v1/portal/tech/telemetry")
def get_tech_telemetry(
    tier: str = Query("T1"),
    unredact_token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    tier_upper = tier.upper()
    if tier_upper not in ["T1", "T2", "T3"]:
        tier_upper = "T1"

    is_unredacted = (tier_upper == "T3" and unredact_token == "AUTH-CA-OVERRIDE-TEMP")

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
            {"worker": "AutonomousScanWorker", "cycle": 1420, "status": "NOMINAL", "latency_ms": 12.4},
            {"worker": "SettlementReconciler", "cycle": 710, "status": "IDLE", "latency_ms": 4.1},
            {"worker": "RateLimiter-Kalshi", "bucket_tokens": 85, "max_tokens": 100, "status": "OPTIMAL"},
            {"worker": "RateLimiter-Polymarket", "bucket_tokens": 92, "max_tokens": 100, "status": "OPTIMAL"}
        ],
        "recent_dispatches": recent_orders,
        "system_metrics": {
            "cpu_load_pct": 8.5,
            "memory_usage_mb": 142.1,
            "active_websockets": 2,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    }

# --- Scoped Portal Copilots & Tutors ---
@router.post("/api/v1/portal/member/ai-tutor")
def member_ai_tutor(query: AssistantQuery):
    q = query.query.lower()
    if "compound" in q or "snowball" in q:
        ans = "Think of compounding as a financial snowball: Every time the engine harvest gains, 87% rolls right back into your cash balance so your next stake has a slightly bigger foundation."
    elif "risk" in q:
        ans = "Your risk dial acts like an engine governor: Dialing down to 1.0% means no individual opportunity will ever commit more than 1% of your available funds."
    else:
        ans = "The PDEUE engine underwrites public events point-in-time and sizes entries defensively using Quarter-Kelly fractions."
    return {"role": "MEMBER_TUTOR", "query": query.query, "response": ans}

@router.post("/api/v1/portal/advisor/copilot")
def advisor_copilot(query: AssistantQuery):
    q = query.query.lower()
    if "withdrawal" in q or "distribution" in q:
        ans = "Fiduciary Impact: Withdrawing $650.00 from Julian's apprentice SCMA reduces 6-month projected compounding velocity by 24.2%. Recommend partial $250.00 distribution under Yellow-Tier."
    elif "rationale" in q or "trade" in q:
        ans = "Trade Analysis: Miami Sub-Freezing contract (KX-MIA-FRZ-32) was backed by 5-member NOAA ASOS ensemble consensus with a 28.5% edge hurdle."
    else:
        ans = "Fiduciary Copilot standing by to assist with lineage liquidity modeling, mentee reviews, and decision audit explanations."
    return {"role": "FIDUCIARY_COPILOT", "query": query.query, "response": ans}

@router.post("/api/v1/portal/tech/copilot")
def tech_copilot(query: AssistantQuery):
    q = query.query.lower()
    if "rate" in q or "limit" in q:
        ans = "Rate Limiter Telemetry: Kalshi token bucket is at 85% capacity; Polymarket is at 92%. Current consumption is well within safe thresholds."
    elif "latency" in q or "worker" in q:
        ans = "Worker Diagnostic: AutonomousScanWorker average round-trip ping is 12.4ms across 1,420 cycles. Zero preemption collisions."
    else:
        ans = "DevOps Telemetry Copilot active. Monitoring daemon cycles, event queues, and WebSocket latency under Directive R-12."
    return {"role": "DEVOPS_COPILOT", "query": query.query, "response": ans}

__all__ = ["router", "portal_router", "LINEAGE_DATA"]
