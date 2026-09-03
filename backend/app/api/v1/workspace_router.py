from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import pathlib
from app.domain.operator_workspace import OperatorWorkspaceService

workspace_router = APIRouter()
_service = OperatorWorkspaceService()

@workspace_router.get('/dashboard', response_class=HTMLResponse)
def get_dashboard():
    html_path = pathlib.Path(__file__).parent.parent.parent / 'static' / 'dashboard.html'
    return HTMLResponse(content=html_path.read_text(encoding='utf-8'))

@workspace_router.get('/api/v1/operator/workspace-state')
def get_workspace_state():
    return _service.get_workspace_state()

@workspace_router.post('/api/v1/operator/emergency-stop')
def post_emergency_stop():
    return _service.trigger_emergency_kill_switch(actor_id='CHIEF_ADMIN', reason='Operator kill-switch triggered from Web Workspace')
