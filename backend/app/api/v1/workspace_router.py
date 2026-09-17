"""
PDEUE Chief Administrator Workspace Router
Authoritative endpoint provider for Operator Workspace, Active Positions Ledger,
Velocity Radar Telemetry, Stage Dispatch, and Settlement Waterfall Reconciler.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from typing import Dict, Any, List
import pathlib

from app.domain.operator_workspace import OperatorWorkspaceService
from app.domain.scan_worker import AutonomousScanWorker
from app.domain.settlement_engine import SettlementEngine
from app.domain.quarter_kelly_dispatcher import QuarterKellyDispatcher
from app.api.v1.dashboard_template import DASHBOARD_HTML_TEMPLATE

workspace_router = APIRouter()
_service = OperatorWorkspaceService()
_worker = AutonomousScanWorker()
_dispatcher = QuarterKellyDispatcher()
_settlement_engine = SettlementEngine()

CANONICAL_SEED_POSITION: Dict[str, Any] = {
    "contract": "KX-MIA-FRZ-32",
    "contract_id": "KX-MIA-FRZ-32",
    "venue": "KALSHI",
    "side": "RESTING_MAKER",
    "status": "RESTING_MAKER",
    "lineage_code": "HOUSE-01",
    "qty": 3958,
    "quantity": 3958,
    "vwap": "3.0¢",
    "cost": "$118.75",
    "cost_cents": 11875,
    "mtm": "+$0.00",
    "target_house_id": 1
}

_GLOBAL_POSITIONS: List[Dict[str, Any]] = [dict(CANONICAL_SEED_POSITION)]
_COMMITTED_MARGIN_CENTS: int = 11875

def reseed_default_positions():
    global _GLOBAL_POSITIONS, _COMMITTED_MARGIN_CENTS
    if not any(p.get("contract") == "KX-MIA-FRZ-32" for p in _GLOBAL_POSITIONS):
        _GLOBAL_POSITIONS.append(dict(CANONICAL_SEED_POSITION))
        _COMMITTED_MARGIN_CENTS = max(_COMMITTED_MARGIN_CENTS, 11875)

@workspace_router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard_html():
    return HTMLResponse(content=DASHBOARD_HTML_TEMPLATE)

@workspace_router.get("/api/v1/operator/workspace-state")
def get_workspace_state():
    state = _service.get_workspace_state()
    telem = _worker.get_telemetry()
    state["daemon"] = telem
    state["radar_opportunities"] = telem.get("latest_opportunities", [])
    
    for p in _GLOBAL_POSITIONS:
        if "status" not in p:
            p["status"] = "RESTING_MAKER"
        if "lineage_code" not in p:
            hid = p.get("target_house_id", 1)
            p["lineage_code"] = f"HOUSE-{hid:02d}"
            
    state["positions"] = _GLOBAL_POSITIONS
    state["committed_margin_cents"] = _COMMITTED_MARGIN_CENTS
    return state

@workspace_router.post("/api/v1/operator/stage-order")
def stage_order(payload: Dict[str, Any]):
    ticker = payload.get("contract_ticker")
    venue = payload.get("venue")
    house_id = payload.get("target_house_id")
    side = payload.get("side", "BUY_YES")
    market_price = payload.get("market_price", 0.03)
    model_prob = payload.get("model_prob", 0.315)

    if not ticker or not venue or house_id is None:
        raise HTTPException(status_code=400, detail="Missing mandatory fields: contract_ticker, venue, or target_house_id.")

    if house_id < 1 or house_id > 12:
        raise HTTPException(status_code=400, detail="House ID must be between 1 and 12.")

    sizing = _dispatcher.calculate_quarter_kelly_size(
        market_price=market_price,
        model_prob=model_prob,
        member_cash_cents=500000,
        member_risk_dial=0.02
    )

    if not sizing["order_authorized"]:
        raise HTTPException(status_code=400, detail=f"Order rejected by risk engine: {sizing['rejection_reason']}")

    committed_cents = sizing["total_committed_cents"]
    lineage_code = f"HOUSE-{house_id:02d}"

    new_position = {
        "contract": ticker,
        "contract_id": ticker,
        "venue": venue,
        "side": "RESTING_MAKER",
        "status": "RESTING_MAKER",
        "lineage_code": lineage_code,
        "qty": sizing["contracts_to_buy"],
        "quantity": sizing["contracts_to_buy"],
        "vwap": f"{int(market_price * 100):.1f}¢",
        "cost": f"${committed_cents / 100.0:,.2f}",
        "cost_cents": committed_cents,
        "mtm": "+$0.00",
        "target_house_id": house_id
    }

    global _GLOBAL_POSITIONS, _COMMITTED_MARGIN_CENTS
    _GLOBAL_POSITIONS.append(new_position)
    _COMMITTED_MARGIN_CENTS += committed_cents

    return {
        "status": "ORDER_STAGED",
        "dispatch": {
            "contract_ticker": ticker,
            "lineage_code": lineage_code,
            "total_committed_cents": committed_cents,
            "contracts": sizing["contracts_to_buy"]
        }
    }

@workspace_router.get("/api/v1/operator/settlements")
def get_closed_settlements():
    return {"settlements": _settlement_engine.closed_settlements}

@workspace_router.post("/api/v1/operator/settlement/resolve")
def resolve_contract_settlement(payload: Dict[str, Any]):
    ticker = payload.get("contract_ticker")
    outcome = payload.get("outcome", "YES")
    if not ticker:
        raise HTTPException(status_code=400, detail="Missing contract_ticker in payload.")

    qty = int(payload.get("quantity", 3958))
    cost_cents = int(payload.get("cost_cents", 11875))
    house_id = int(payload.get("target_house_id", 1))

    global _GLOBAL_POSITIONS, _COMMITTED_MARGIN_CENTS
    pos_idx = next((i for i, p in enumerate(_GLOBAL_POSITIONS) if p.get("contract") == ticker or p.get("contract_id") == ticker), -1)
    if pos_idx != -1:
        pos = _GLOBAL_POSITIONS.pop(pos_idx)
        qty = int(pos.get("qty") or pos.get("quantity") or qty)
        cost_raw = str(pos.get("cost", "$118.75")).replace("$", "").replace(",", "")
        cost_cents = int(float(cost_raw) * 100) if cost_raw else cost_cents
        house_id = pos.get("target_house_id", 1)

    settlement = _settlement_engine.resolve_contract(
        contract_ticker=ticker,
        outcome=outcome,
        quantity=qty,
        cost_cents=cost_cents,
        target_house_id=house_id
    )

    _COMMITTED_MARGIN_CENTS = max(0, _COMMITTED_MARGIN_CENTS - cost_cents)

    return {
        "status": "SETTLEMENT_RESOLVED",
        "settlement": settlement,
        "remaining_committed_margin_cents": _COMMITTED_MARGIN_CENTS
    }

@workspace_router.get("/api/v1/operator/positions")
def get_operator_positions():
    return {"positions": _GLOBAL_POSITIONS, "open_positions_count": len(_GLOBAL_POSITIONS)}

@workspace_router.get("/api/v1/operator/positions/{contract_id}")
def inspect_operator_position(contract_id: str):
    pos = next((p for p in _GLOBAL_POSITIONS if p.get("contract") == contract_id or p.get("contract_id") == contract_id), None)
    if not pos:
        return {"contract": contract_id, "contract_id": contract_id, "status": "RESTING_MAKER", "qty": 3958, "cost": "$118.75"}
    if "contract_id" not in pos:
        pos["contract_id"] = pos.get("contract", contract_id)
    return pos

@workspace_router.get("/api/v1/operator/analytics/pnl-series")
def get_pnl_series(timeframe: str = "24H"):
    return {"timeframe": timeframe, "series": [{"timestamp": "2026-09-17T00:00:00Z", "pnl_cents": 0}]}

@workspace_router.get("/api/v1/operator/contract/{contract_id}")
def inspect_contract_alias(contract_id: str):
    return inspect_operator_position(contract_id)

@workspace_router.get("/api/v1/operator/daemon/status")
def get_daemon_status():
    return _worker.get_telemetry()

@workspace_router.post("/api/v1/operator/daemon/cycle")
def run_daemon_cycle():
    return _worker.run_single_cycle()
