"""
PDEUE Operator Workspace Router
Authoritative endpoints for operator workspace state, daemon telemetry,
kill-switch execution, and position ledger access.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from typing import Dict, Any, Optional
from app.domain.operator_workspace import OperatorWorkspaceService
from app.domain.scan_worker import AutonomousScanWorker
from app.domain.quarter_kelly_dispatcher import QuarterKellyDispatcher
from app.api.v1.dashboard_template import DASHBOARD_HTML_TEMPLATE

workspace_router = APIRouter(tags=["Operator Workspace"])
_service = OperatorWorkspaceService()
_worker = AutonomousScanWorker()
_position_book = _service.position_book
_dispatcher = QuarterKellyDispatcher()

@workspace_router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard_html():
    return HTMLResponse(content=DASHBOARD_HTML_TEMPLATE)

@workspace_router.get("/api/v1/operator/workspace-state")
def get_workspace_state():
    state = _service.get_workspace_state()
    tel = _worker.get_telemetry()
    state["daemon"] = tel
    state["radar_opportunities"] = tel.get("latest_opportunities", [])
    return state

@workspace_router.post("/api/v1/operator/emergency-stop")
def trigger_emergency_stop():
    return _service.trigger_emergency_stop(actor_id="CHIEF_ADMIN", reason="Dashboard Kill Switch Activated")

@workspace_router.get("/api/v1/operator/positions")
def get_positions():
    return _service.position_book.get_summary()

@workspace_router.get("/api/v1/operator/contract/{contract_id}")
def inspect_contract(contract_id: str):
    return _service.get_contract_inspection(contract_id)

@workspace_router.get("/api/v1/operator/analytics/pnl-series")
def get_pnl_series(timeframe: str = Query("24H")):
    return _service.get_pnl_time_series(timeframe=timeframe)

@workspace_router.post("/api/v1/operator/governance/dual-approve")
def dual_approve(payload: Dict[str, Any]):
    aid = payload.get("action_id", "")
    approver = payload.get("approver_id", "T3-SEC-OFFICER")
    role = payload.get("approver_role", "T3_SYSTEM_ADMIN")
    return _service.approve_dual_control_action(action_id=aid, approver_id=approver, approver_role=role)

@workspace_router.get("/api/v1/operator/daemon/status")
def get_daemon_status():
    return _worker.get_telemetry()

@workspace_router.post("/api/v1/operator/daemon/start")
def start_daemon():
    _worker.start()
    tel = _worker.get_telemetry()
    tel["status"] = "STARTED"
    return tel

@workspace_router.post("/api/v1/operator/daemon/stop")
def stop_daemon():
    _worker.stop()
    tel = _worker.get_telemetry()
    tel["status"] = "STOPPED"
    return tel

@workspace_router.post("/api/v1/operator/daemon/cycle")
def run_daemon_cycle():
    return _worker.run_single_cycle()

@workspace_router.post("/api/v1/operator/stage-order")
def stage_order(payload: Dict[str, Any]):
    ticker = payload.get("contract_ticker", payload.get("ticker", "KX-MIA-FRZ-32"))
    venue = payload.get("venue", "KALSHI")
    house_id = int(payload.get("target_house_id", payload.get("house_id", 1)))
    side = payload.get("side", "BUY_YES")
    price = float(payload.get("market_price", payload.get("price", 0.03)))
    prob = float(payload.get("model_prob", 0.315))

    if house_id < 1 or house_id > 12:
        raise HTTPException(status_code=400, detail="House ID must be between 1 and 12.")

    dispatch = _dispatcher.dispatch_opportunity(
        contract_ticker=ticker,
        venue=venue,
        target_house_id=house_id,
        side=side,
        market_price=price,
        model_prob=prob
    )

    # Register into active position ledger
    pos_record = {
        "contract": ticker,
        "venue": venue,
        "side": side,
        "qty": dispatch["total_quantity"],
        "vwap": f"{int(round(price * 100))}¢",
        "cost": f"${dispatch['total_committed_cents'] / 100.0:.2f}",
        "mtm": "+$0.00",
        "status": "RESTING_MAKER",
        "lineage_code": dispatch["lineage_code"]
    }
    
    # Store on position book if positions attribute is accessible
    if hasattr(_position_book, "positions") and isinstance(_position_book.positions, dict):
        _position_book.positions[ticker] = pos_record

    return {
        "status": "ORDER_STAGED",
        "dispatch": dispatch,
        "position_record": pos_record
    }

@workspace_router.get("/api/v1/operator/roster")
def get_roster():
    state = _service.get_workspace_state()
    return {"status": "SUCCESS", "roster": state.get("roster", [])}

__all__ = ["workspace_router", "_service", "_worker", "_position_book"]
