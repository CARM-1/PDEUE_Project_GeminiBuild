from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from typing import Dict, Any, Optional
from app.domain.operator_workspace import OperatorWorkspaceService
from app.domain.scan_worker import AutonomousScanWorker
from app.api.v1.dashboard_template import DASHBOARD_HTML_TEMPLATE

workspace_router = APIRouter()
_service = OperatorWorkspaceService()
_worker = AutonomousScanWorker()

@workspace_router.get('/dashboard', response_class=HTMLResponse)
def get_dashboard_html():
    return HTMLResponse(content=DASHBOARD_HTML_TEMPLATE)

@workspace_router.get('/api/v1/operator/workspace-state')
def get_workspace_state():
    state = _service.get_workspace_state()
    state['daemon'] = _worker.get_telemetry()
    return state

@workspace_router.post('/api/v1/operator/emergency-stop')
def trigger_emergency_stop():
    return _service.trigger_emergency_stop(actor_id='CHIEF_ADMIN', reason='Dashboard Kill Switch Activated')

@workspace_router.get('/api/v1/operator/positions')
def get_positions():
    return _service.position_book.get_summary()

@workspace_router.get('/api/v1/operator/contract/{contract_id}')
def inspect_contract(contract_id: str):
    return _service.get_contract_inspection(contract_id)

@workspace_router.get('/api/v1/operator/analytics/pnl-series')
def get_pnl_series(timeframe: str = Query('24H')):
    return _service.get_pnl_time_series(timeframe=timeframe)

@workspace_router.post('/api/v1/operator/governance/dual-approve')
def dual_approve(payload: Dict[str, Any]):
    aid = payload.get('action_id', '')
    approver = payload.get('approver_id', 'T3-SEC-OFFICER')
    role = payload.get('approver_role', 'T3_SYSTEM_ADMIN')
    return _service.approve_dual_control_action(action_id=aid, approver_id=approver, approver_role=role)

@workspace_router.get('/api/v1/operator/daemon/status')
def get_daemon_status():
    return _worker.get_telemetry()

@workspace_router.post('/api/v1/operator/daemon/start')
def start_daemon():
    _worker.start()
    tel = _worker.get_telemetry()
    tel['status'] = 'STARTED'
    return tel

@workspace_router.post('/api/v1/operator/daemon/stop')
def stop_daemon():
    _worker.stop()
    tel = _worker.get_telemetry()
    tel['status'] = 'STOPPED'
    return tel

@workspace_router.post('/api/v1/operator/daemon/cycle')
def run_daemon_cycle():
    return _worker.run_single_cycle()
