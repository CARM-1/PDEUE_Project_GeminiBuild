from fastapi.testclient import TestClient
from app.main import app
from app.domain.operator_workspace import OperatorWorkspaceService

def test_workspace_service_state_aggregation():
    service = OperatorWorkspaceService()
    state = service.get_workspace_state()
    assert state['operating_mode'] == 'PAPER'
    assert state['circuit_breaker']['is_tripped'] is False
    assert state['ledger']['available_balance_cents'] == 10000000
    assert len(state['opportunities']) >= 1

def test_workspace_service_emergency_kill_switch():
    service = OperatorWorkspaceService()
    service.trigger_emergency_kill_switch(actor_id='ADMIN_TEST', reason='Test Trip')
    state = service.get_workspace_state()
    assert state['operating_mode'] == 'HALTED'
    assert state['circuit_breaker']['is_tripped'] is True

def test_workspace_api_endpoints():
    client = TestClient(app)
    resp = client.get('/dashboard')
    assert resp.status_code == 200
    assert 'PDEUE Chief Administrator Workspace' in resp.text

    state_resp = client.get('/api/v1/operator/workspace-state')
    assert state_resp.status_code == 200
    json_data = state_resp.json()
    assert 'operating_mode' in json_data
    assert 'ledger' in json_data
