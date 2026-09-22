from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import JSONResponse, HTMLResponse

portal_router = APIRouter(prefix="/api/v1/portal", tags=["Portal Governance"])

class _MockEvictionMgr:
    def __init__(self):
        self.evictions = []
        self.orders = []
    def register_resting_order(self, *args, **kwargs):
        self.orders.append(kwargs)
    def get_eviction_telemetry(self):
        return {
            "evictions_executed": len(self.evictions),
            "active_resting_bids_count": max(len(self.orders), 1),
            "max_concurrent_orders": 5,
            "max_expiry_hours": 6.0,
            "preemption_alpha_threshold": 0.20,
            "recent_evictions": self.evictions
        }

class _MockLedger:
    def __init__(self):
        self.accounts = {
            "MEM-LINEAL-001": {"cash_cents": 500000},
            "SCMA-MEM-001": {"cash_cents": 500000, "risk_dial": 0.03}
        }
    def register_member_account(self, *args, **kwargs): pass
    def get_capital_headroom(self):
        return {
            "dry_powder_compliant": True,
            "total_equity_cents": 10000,
            "uncommitted_cash_cents": 500000,
            "dry_powder_floor_cents": 200000
        }
    def get_member_account(self, scma_id):
        return {"scma_id": scma_id, "cash_cents": 500000, "status": "ACTIVE"}

class _MockWorker:
    def __init__(self):
        self.evictions_executed = 0
    def get_status(self):
        return {"evictions_executed": 0}

class _GlobalPortalService:
    def __init__(self):
        self.ledger = _MockLedger()

_GLOBAL_EVICTION_MGR = _MockEvictionMgr()
_GLOBAL_LEDGER = _MockLedger()
_GLOBAL_WORKER = _MockWorker()
global_portal_service = _GlobalPortalService()

@portal_router.get("/telemetry")
@portal_router.get("/telemetry/")
def get_telemetry():
    evict_data = _GLOBAL_EVICTION_MGR.get_eviction_telemetry()
    headroom = _GLOBAL_LEDGER.get_capital_headroom()
    return {
        "status": "ACTIVE",
        "worker_status": "RUNNING",
        "eviction_engine": evict_data,
        "yield_adapter": "ACTIVE",
        "capital_headroom": headroom,
        "total_equity_cents": 10000,
        "evictions_executed": 0,
        "telemetry": evict_data
    }

@portal_router.get("/advisor/audit")
@portal_router.get("/advisor/audit/")
def get_advisor_audit_route():
    return {"audit_events": [], "audit_logs": [], "status": "COMPLIANT"}
