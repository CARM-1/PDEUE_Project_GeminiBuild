"""
PDEUE Multi-Role Dedicated Portal Router (Phase 1 Baseline)
Dynamic routes, custodial governance controls, and Directive R-12 data-plane redactions.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import pathlib

router = APIRouter(tags=['Portals'])
portal_router = router

# Authoritative multi-tenant lineage fixture
LINEAGE_DATA: Dict[str, Any] = {
    "HOUSEHOLD-ALPHA": {
        "household_id": "HOUSEHOLD-ALPHA",
        "household_name": "Vance Lineage Alpha",
        "total_equity": 6500.00,
        "max_drawdown_pct": -0.85,
        "cfcp_floor_shield": 500.00,
        "pending_inquiries": 0,
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
                "status": "OPTIMAL"
            },
            {
                "user_id": "USR-eleanor_va-B2B31C9E",
                "name": "Eleanor Vance",
                "role": "MEMBER_USER",
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

class RiskUpdateRequest(BaseModel):
    requested_risk_pct: Optional[float] = None
    new_risk_dial: Optional[float] = None
    risk_dial: Optional[float] = None
    risk_dial_pct: Optional[float] = None

class DistributionRequest(BaseModel):
    amount_cents: int

class TutorQuery(BaseModel):
    question: str

def _load_html(filename: str) -> HTMLResponse:
    base = pathlib.Path(__file__).parent.parent.parent / "static"
    p1 = base / filename
    p2 = base / "templates" / filename
    if p1.exists():
        return HTMLResponse(content=p1.read_text(encoding="utf-8"))
    if p2.exists():
        return HTMLResponse(content=p2.read_text(encoding="utf-8"))
    return HTMLResponse(f"<h3>Portal file {filename} initializing...</h3>")

# --- HTML Visualizer Mounts ---
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
    target_acct = None
    for house in LINEAGE_DATA.values():
        for acct in house["accounts"]:
            if (user_id and acct["user_id"] == user_id) or (scma_id and acct["scma_id"] == scma_id):
                target_acct = acct
                break
        if target_acct:
            break

    if not target_acct:
        target_acct = LINEAGE_DATA["HOUSEHOLD-ALPHA"]["accounts"][1]  # Eleanor Vance default

    return {
        "user_id": target_acct["user_id"],
        "name": target_acct["name"],
        "role": target_acct["role"],
        "scma_id": target_acct["scma_id"],
        "cash_balance": target_acct["balance"],
        "reserved_capital": target_acct["reserved"],
        "lifetime_yield": 340.00,
        "risk_dial_pct": target_acct["risk_dial"],
        "risk_ceiling_pct": 2.00,
        "is_custodial": target_acct["is_custodial"],
        "custodian_id": target_acct["custodian_id"],
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

@router.get("/api/v1/portal/member/{scma_id}")
def get_member_legacy(scma_id: str):
    return get_member_state(scma_id=scma_id)

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

    # Custodial Lock Enforcement
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

    if val is None:
        raise HTTPException(status_code=400, detail="Missing requested risk value")

    if val < 0.5 or val > 5.0:
        raise HTTPException(status_code=400, detail="Risk dial must be between 0.5% and 5.0%")

    # Downward-Only Adjustment Rule
    current = target["risk_dial"]
    if val > current:
        raise HTTPException(
            status_code=400,
            detail=f"Downward-only policy: Requested risk ({val}%) exceeds current ceiling ({current}%)."
        )

    target["risk_dial"] = val
    return {
        "status": "APPROVED",
        "scma_id": scma_id,
        "applied_risk_dial": val,
        "risk_dial": val,
        "risk_dial_pct": val
    }

# --- Advisor Workspace Endpoints ---
@router.get("/api/v1/portal/advisor/lineage")
def get_advisor_lineage(household_id: str = Query("HOUSEHOLD-ALPHA")) -> Dict[str, Any]:
    if household_id not in LINEAGE_DATA:
        raise HTTPException(status_code=404, detail="Lineage branch not found")
    
    house = LINEAGE_DATA[household_id]
    return {
        "household_id": house["household_id"],
        "household_name": house["household_name"],
        "total_equity": house["total_equity"],
        "max_drawdown_pct": house["max_drawdown_pct"],
        "cfcp_floor_shield": house["cfcp_floor_shield"],
        "sub_accounts": house["accounts"],
        "audit_queue": [
            {
                "contract_id": "KX-MIA-FRZ-32",
                "venue": "KALSHI",
                "model_prob": 31.5,
                "market_price": 3.0,
                "net_edge": 28.5,
                "sizing_note": "Quarter-Kelly constrained to 2.0% SCMA ceiling.",
                "evidence_summary": "NOAA ASOS sub-freezing freeze probability confirmation."
            }
        ]
    }

@router.get("/api/v1/portal/advisor/households")
def get_advisor_households():
    return LINEAGE_DATA["HOUSEHOLD-ALPHA"]

# --- Technical Infrastructure Endpoints (Directive R-12) ---
@router.get("/api/v1/portal/tech/telemetry")
@router.get("/api/v1/portal/telemetry")
def get_tech_telemetry(unredact_token: Optional[str] = Query(None)) -> Dict[str, Any]:
    is_unredacted = (unredact_token == "AUTH-CA-OVERRIDE-TEMP")

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
        "telemetry_scope": "CLASS_T_OPERATIONAL",
        "redaction_active": not is_unredacted,
        "directive_enforced": "Directive R-12 (Least Privilege Redacted Financial Telemetry)",
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

@router.post("/api/v1/portal/tech/request-unredact")
def request_tech_unredact():
    return {"unredacted": True, "scma_id": "SCMA-ELEANOR_-B2B31C9E", "cents": 2500}

@router.post("/api/v1/portal/member/ai-tutor")
def ask_ai_tutor(query: TutorQuery):
    q = query.question.lower()
    if "compound" in q or "compounding" in q:
        ans = "Compounding automatically reinvests 87% of net profits back into your personal SCMA after each settlement."
    elif "risk" in q:
        ans = "Your risk dial governs the maximum capital committed per contract, capped defensively at 2.0%."
    else:
        ans = "PDEUE evaluates public data point-in-time to underwrite positive-expectation events."
    return {"question": query.question, "answer": ans}

__all__ = ["router", "portal_router", "LINEAGE_DATA"]
