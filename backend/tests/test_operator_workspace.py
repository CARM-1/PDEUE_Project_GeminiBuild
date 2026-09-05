from fastapi.testclient import TestClient
from app.main import app
from app.domain.operator_workspace import OperatorWorkspaceService
from app.domain.circuit_breaker import CircuitBreakerEngine

def test_workspace_service_state_aggregation():
    service = OperatorWorkspaceService()
    state = service.get_workspace_state()
    assert 'system_mode' in state
    assert 'founder_scma' in state
    assert 'cfcp_cents' in state
    assert 'faep_cents' in state
    assert 'metrics' in state
    assert state['metrics']['profit_factor'] >= 1.0

def test_workspace_service_emergency_kill_switch():
    cb = CircuitBreakerEngine()
    service = OperatorWorkspaceService(circuit_breaker=cb)
    res = service.trigger_emergency_stop(actor_id='CHIEF_ADMIN')
    assert cb.validate_execution_allowed() is False
    assert res['action'] == 'CIRCUIT_BREAKER_TRIPPED'

def test_workspace_api_endpoints():
    client = TestClient(app)
    resp = client.get('/dashboard')
    assert resp.status_code == 200
    assert 'PDEUE Chief Administrator Workspace' in resp.text
    state_resp = client.get('/api/v1/operator/workspace-state')
    assert state_resp.status_code == 200
    data = state_resp.json()
    assert 'founder_scma' in data
    assert 'metrics' in data
    inspect_resp = client.get('/api/v1/operator/contract/KX-ORD-26')
    assert inspect_resp.status_code == 200
    assert inspect_resp.json()['contract_id'] == 'KX-ORD-26'
    pnl_resp = client.get('/api/v1/operator/analytics/pnl-series?timeframe=24H')
    assert pnl_resp.status_code == 200
    assert len(pnl_resp.json()['labels']) > 0
    dual_resp = client.post('/api/v1/operator/governance/dual-approve', json={'action_id': 'TEST'})
    assert dual_resp.status_code == 200
