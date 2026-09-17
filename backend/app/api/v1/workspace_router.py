"""
PDEUE Operator Workspace Router
Unifies operator cockpit state, Velocity Radar live streaming,
Quarter-Kelly lineage order dispatching, and active portfolio ledger synchronization.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from typing import Dict, Any, Optional, List
from app.domain.operator_workspace import OperatorWorkspaceService
from app.domain.scan_worker import AutonomousScanWorker
from app.domain.quarter_kelly_dispatcher import QuarterKellyDispatcher
from app.api.v1.dashboard_template import DASHBOARD_HTML_TEMPLATE

workspace_router = APIRouter()
_service = OperatorWorkspaceService()
_worker = AutonomousScanWorker()
_dispatcher = QuarterKellyDispatcher()
_position_book = getattr(_service, "position_book", None)
_staged_portfolio_orders: List[Dict[str, Any]] = []

@workspace_router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard_html():
    return HTMLResponse(content=DASHBOARD_HTML_TEMPLATE)

@workspace_router.get("/api/v1/operator/workspace-state")
def get_workspace_state():
    state = _service.get_workspace_state()
    tel = _worker.get_telemetry()
    state["daemon"] = tel
    state["radar_opportunities"] = tel.get("latest_opportunities", [])

    # Ensure state["positions"] is initialized as a list
    if "positions" not in state or not isinstance(state["positions"], list):
        if _position_book is not None and hasattr(_position_book, "positions"):
            state["positions"] = list(_position_book.positions.values())
        else:
            state["positions"] = []

    # Merge staged ledger positions into Tab 1 active view
    active_ids = {p.get("contract") or p.get("contract_id") for p in state["positions"]}
    for staged in _staged_portfolio_orders:
        staged_id = staged.get("contract") or staged.get("contract_id")
        if staged_id not in active_ids:
            state["positions"].insert(0, staged)
            active_ids.add(staged_id)

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

    pos_record = {
        "contract": ticker,
        "contract_id": ticker,
        "venue": venue,
        "side": side,
        "qty": dispatch["total_quantity"],
        "quantity": dispatch["total_quantity"],
        "vwap": f"{int(round(price * 100))}¢",
        "cost": f"${dispatch['total_committed_cents'] / 100.0:.2f}",
        "mtm": "+$0.00",
        "status": "RESTING_MAKER",
        "lineage_code": dispatch["lineage_code"],
        "total_cost_cents": dispatch["total_committed_cents"],
        "mtm_value_cents": dispatch["total_committed_cents"],
        "unrealized_pnl_cents": 0,
        "realized_pnl_cents": 0
    }

    if _position_book is not None and hasattr(_position_book, "positions") and isinstance(_position_book.positions, dict):
        _position_book.positions[ticker] = pos_record

    _staged_portfolio_orders.append(pos_record)

    return {
        "status": "ORDER_STAGED",
        "dispatch": dispatch,
        "position_record": pos_record
    }
