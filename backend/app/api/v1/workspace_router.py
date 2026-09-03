from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import pathlib
from app.domain.operator_workspace import OperatorWorkspaceService
from app.domain.scan_worker import AutonomousScanWorker

workspace_router = APIRouter()
_service = OperatorWorkspaceService()
_worker = AutonomousScanWorker(circuit_breaker=_service.circuit_breaker)

@workspace_router.get('/dashboard', response_class=HTMLResponse)
def get_dashboard():
    html_path = pathlib.Path(__file__).parent.parent.parent / 'static' / 'dashboard.html'
    return HTMLResponse(content=html_path.read_text(encoding='utf-8'))

@workspace_router.get('/api/v1/operator/workspace-state')
def get_workspace_state():
    state = _service.get_workspace_state()
    state['daemon'] = _worker.get_telemetry()
    return state

@workspace_router.post('/api/v1/operator/emergency-stop')
def post_emergency_stop():
    _worker.stop()
    return _service.trigger_emergency_kill_switch(actor_id='CHIEF_ADMIN', reason='Operator kill-switch triggered from Web Workspace')

@workspace_router.get('/api/v1/operator/daemon/status')
def get_daemon_status():
    return _worker.get_telemetry()

@workspace_router.post('/api/v1/operator/daemon/start')
def start_daemon():
    _worker.start()
    return {'status': 'STARTED', 'telemetry': _worker.get_telemetry()}

@workspace_router.post('/api/v1/operator/daemon/stop')
def stop_daemon():
    _worker.stop()
    return {'status': 'STOPPED', 'telemetry': _worker.get_telemetry()}

@workspace_router.post('/api/v1/operator/daemon/cycle')
def trigger_daemon_cycle():
    return _worker.run_single_cycle()
