from fastapi.testclient import TestClient
from app.main import app
from app.domain.capital_ledger import CapitalLedger
from app.api.v1.portal_router import global_portal_service

def test_member_portal_downward_only_risk_dial():
    client = TestClient(app)
    ledger = global_portal_service.ledger
    ledger.register_member_account('SCMA-PORTAL-01', seed_capital_cents=50000, max_risk_pct=0.04)

    # Downward adjustment: 0.04 -> 0.02 (Valid)
    res = client.post('/api/v1/portal/member/SCMA-PORTAL-01/risk-dial', json={'requested_risk_pct': 0.02})
    assert res.status_code == 200
    assert res.json()['new_risk_pct'] == 0.02

    # Upward adjustment: 0.02 -> 0.05 (Must Be Rejected)
    res_reject = client.post('/api/v1/portal/member/SCMA-PORTAL-01/risk-dial', json={'requested_risk_pct': 0.05})
    assert res_reject.status_code == 400
    assert 'downward-only' in res_reject.json()['detail'].lower()

def test_member_distribution_queue_and_isolation():
    client = TestClient(app)
    ledger = global_portal_service.ledger
    ledger.register_member_account('SCMA-PORTAL-02', seed_capital_cents=20000, max_risk_pct=0.03)

    # Request distribution within balance
    res = client.post('/api/v1/portal/member/SCMA-PORTAL-02/distribution', json={'amount_cents': 5000})
    assert res.status_code == 200
    assert res.json()['status'] == 'QUEUED'

    # Over-balance distribution rejection
    res_over = client.post('/api/v1/portal/member/SCMA-PORTAL-02/distribution', json={'amount_cents': 500000})
    assert res_over.status_code == 400

def test_advisor_household_read_boundary():
    client = TestClient(app)
    ledger = global_portal_service.ledger
    ledger.register_member_account('HH-MEM-1', seed_capital_cents=10000, max_risk_pct=0.03)
    ledger.register_member_account('HH-MEM-2', seed_capital_cents=20000, max_risk_pct=0.02)

    res = client.get('/api/v1/portal/advisor/household/HH-ALPHA?members=HH-MEM-1&members=HH-MEM-2')
    assert res.status_code == 200
    data = res.json()
    assert data['member_count'] == 2
    assert data['total_valuation_cents'] == 30000
