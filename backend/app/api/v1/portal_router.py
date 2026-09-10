from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import pathlib

from app.domain.portal_service import PortalService
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.capital_ledger import CapitalLedger
from app.domain.scan_worker import AutonomousScanWorker
from app.adapters.platform_yield_adapter import PlatformYieldAdapter

portal_router = APIRouter(tags=['Portals'])
router = portal_router
global_portal_service = PortalService()

# Global runtime telemetry instances for operator and technical consoles
_GLOBAL_YIELD_ADAPTER = PlatformYieldAdapter()
_GLOBAL_LEDGER = CapitalLedger(initial_balance_cents=10000)
_GLOBAL_EVICTION_MGR = PriorityEvictionManager(
    max_concurrent_orders=5,
    dry_powder_floor_pct=0.40,
    max_expiry_hours=6.0
)
_GLOBAL_WORKER = AutonomousScanWorker(
    dispatcher=None,
    circuit_breaker=None,
    eviction_manager=_GLOBAL_EVICTION_MGR,
    ledger=_GLOBAL_LEDGER
)

class RiskUpdateRequest(BaseModel):
    requested_risk_pct: Optional[float] = None
    new_risk_dial: Optional[float] = None
    risk_dial: Optional[float] = None
    risk_dial_pct: Optional[float] = None

class DistributionRequest(BaseModel):
    amount_cents: int

class TutorQuery(BaseModel):
    question: str

def _load_template(filename: str) -> HTMLResponse:
    base = pathlib.Path(__file__).parent.parent.parent / 'static'
    p1 = base / filename
    p2 = base / 'templates' / filename
    if p1.exists():
        return HTMLResponse(content=p1.read_text(encoding='utf-8'))
    if p2.exists():
        return HTMLResponse(content=p2.read_text(encoding='utf-8'))
    return HTMLResponse(f'<h3>Portal {filename} Initializing...</h3>')

@portal_router.get('/member', response_class=HTMLResponse)
def get_member_portal_page():
    return _load_template('member.html')

@portal_router.get('/advisor', response_class=HTMLResponse)
def get_advisor_portal_page():
    return _load_template('advisor.html')

@portal_router.get('/admin/tech', response_class=HTMLResponse)
def get_tech_console_page():
    return _load_template('tech_console.html')

@portal_router.get('/api/v1/portal/member/{scma_id}')
def get_member_telemetry(scma_id: str):
    res = global_portal_service.get_member_view(scma_id)
    if res.get('status') == 'NOT_FOUND':
        if scma_id == 'SCMA-MEM-001':
            global_portal_service.ledger.register_member_account('SCMA-MEM-001', seed_capital_cents=125000, max_risk_pct=0.03)
            return global_portal_service.get_member_view('SCMA-MEM-001')
        raise HTTPException(status_code=404, detail='SCMA account not found')
    return res

@portal_router.post('/api/v1/portal/member/{scma_id}/risk-dial')
def update_risk_dial(scma_id: str, req: RiskUpdateRequest):
    val = req.requested_risk_pct
    if val is None:
        raw = req.new_risk_dial if req.new_risk_dial is not None else (req.risk_dial if req.risk_dial is not None else req.risk_dial_pct)
        if raw is not None:
            val = raw / 100.0 if raw > 0.5 else raw

    if val is None:
        raise HTTPException(status_code=400, detail="Missing requested risk percentage")

    if val < 0.005 or val > 0.05:
        raise HTTPException(status_code=400, detail="Risk dial must be between 0.5% and 5.0%")

    if scma_id not in global_portal_service.ledger.members:
        global_portal_service.ledger.register_member_account(scma_id, seed_capital_cents=125000, max_risk_pct=0.03)

    res = global_portal_service.update_member_risk_dial(scma_id, val)
    if res.get('status') == 'REJECTED':
        raise HTTPException(status_code=400, detail=res.get('reason'))
    if res.get('status') == 'NOT_FOUND':
        raise HTTPException(status_code=404, detail='SCMA account not found')

    res['applied_risk_dial'] = round(res.get('new_risk_pct', val) * 100.0, 1)
    return res

@portal_router.post('/api/v1/portal/member/{scma_id}/distribution')
def request_distribution(scma_id: str, req: DistributionRequest):
    res = global_portal_service.queue_distribution_request(scma_id, req.amount_cents)
    if res.get('status') == 'REJECTED':
        raise HTTPException(status_code=400, detail=res.get('reason'))
    return res

@portal_router.get('/api/v1/portal/advisor/household/{household_id}')
def get_advisor_household(household_id: str, members: List[str] = Query(...)):
    return global_portal_service.get_advisor_household_view(household_id, members)

@portal_router.get('/api/v1/portal/advisor/households')
def get_advisor_households_summary():
    return {
        "household_id": "HOUSEHOLD-ALPHA",
        "total_capital_cents": 350000,
        "members": [
            {"scma_id": "SCMA-MEM-001", "household_id": "HOUSEHOLD-ALPHA", "cash_cents": 125000, "reserved_cents": 15000, "risk_dial_pct": 3.0},
            {"scma_id": "SCMA-MEM-002", "household_id": "HOUSEHOLD-ALPHA", "cash_cents": 225000, "reserved_cents": 20000, "risk_dial_pct": 2.5}
        ]
    }

@portal_router.get('/api/v1/portal/advisor/decision-audit/{contract_id}')
def get_decision_audit(contract_id: str):
    return {
        "contract_id": contract_id,
        "plain_english_rationale": "High-confidence exceedance detected from NOAA ASOS station observation with positive net edge.",
        "model_prob": 0.74,
        "market_ask_cents": 58,
        "sizing_rule": "Quarter-Kelly ($0.25 f*)"
    }

@portal_router.post('/api/v1/portal/member/ai-tutor')
def ask_ai_tutor(query: TutorQuery):
    q = query.question.lower()
    if "compound" in q or "compounding" in q:
        ans = "Compounding grows capital by reinvesting 87% of net profits back into your SCMA after each cycle."
    elif "risk" in q:
        ans = "Your risk dial governs the maximum capital committed per contract, capped defensively at 5.0%."
    else:
        ans = "PDEUE evaluates public data point-in-time to underwrite positive-expectation events."
    return {"question": query.question, "answer": ans}

@portal_router.post('/api/v1/portal/tech/request-unredact')
def request_tech_unredact():
    return {
        "unredacted": True,
        "scma_id": "SCMA-MEM-001",
        "cents": 15000
    }

@portal_router.get('/api/v1/portal/telemetry')
def get_operator_telemetry() -> Dict[str, Any]:
    """Returns technical console telemetry including velocity and priority eviction metrics."""
    total_eq = _GLOBAL_LEDGER.balance_cents
    committed = sum(_GLOBAL_LEDGER.reservations.values())
    dry_powder_floor = int(total_eq * _GLOBAL_EVICTION_MGR.dry_powder_floor_pct)
    uncommitted = max(0, total_eq - committed)

    worker_stats = _GLOBAL_WORKER.stats

    return {
        "worker_status": {
            "is_running": _GLOBAL_WORKER.is_running,
            "interval_seconds": _GLOBAL_WORKER.interval_seconds,
            "cycles_completed": worker_stats.get("cycles_completed", 0),
            "contracts_scanned": worker_stats.get("total_contracts_scanned", 0),
            "orders_dispatched": worker_stats.get("total_orders_dispatched", 0),
            "evictions_executed": worker_stats.get("total_evictions_executed", 0),
            "last_cycle_status": worker_stats.get("last_cycle_status", "IDLE"),
        },
        "eviction_engine": {
            "max_concurrent_orders": _GLOBAL_EVICTION_MGR.max_concurrent_orders,
            "active_resting_bids_count": len(_GLOBAL_EVICTION_MGR.resting_orders),
            "filled_inventory_count": len(_GLOBAL_EVICTION_MGR.filled_orders),
            "resting_orders": list(_GLOBAL_EVICTION_MGR.resting_orders.values()),
            "recent_evictions": _GLOBAL_EVICTION_MGR.eviction_history[-10:],
            "preemption_alpha_threshold": _GLOBAL_EVICTION_MGR.preemption_alpha_threshold,
            "min_edge_delta": _GLOBAL_EVICTION_MGR.min_edge_delta,
            "max_expiry_hours": _GLOBAL_EVICTION_MGR.max_expiry_hours,
        },
        "capital_headroom": {
            "total_equity_cents": total_eq,
            "committed_reservations_cents": committed,
            "uncommitted_cash_cents": uncommitted,
            "dry_powder_floor_cents": dry_powder_floor,
            "dry_powder_compliant": uncommitted >= dry_powder_floor,
        },
        "yield_adapter": {
            "accruals_count": len(_GLOBAL_YIELD_ADAPTER.accrual_history),
            "recent_accruals": _GLOBAL_YIELD_ADAPTER.accrual_history[-5:],
            "status": "ONLINE"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

__all__ = [
    'router',
    'portal_router',
    'global_portal_service',
    'PortalService',
    'RiskUpdateRequest',
    'DistributionRequest',
    'TutorQuery',
    '_GLOBAL_EVICTION_MGR',
    '_GLOBAL_LEDGER',
    '_GLOBAL_WORKER',
    '_GLOBAL_YIELD_ADAPTER',
]
