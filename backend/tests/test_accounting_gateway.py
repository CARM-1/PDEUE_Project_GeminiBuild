import hashlib
from fastapi.testclient import TestClient
from app.main import app
from app.domain.accounting_gateway import AccountingGateway

def test_accounting_gateway_signature_and_cent_conservation():
    gw = AccountingGateway()
    evt = gw.emit_settlement_event(
        contract_id='KX-ORD-26',
        scma_id='SCMA-001',
        gross_payout_cents=1000,
        scma_net_cents=870,
        cfcp_cents=100,
        faep_cents=30
    )
    assert evt['sequence_id'] == 1
    assert evt['status'] == 'EMITTED'
    canonical_bytes = gw._canonicalize_payload(evt['payload'])
    assert gw.verify_signature(canonical_bytes, evt['signature_hmac_sha256']) is True

def test_cent_conservation_invariant_assertion():
    gw = AccountingGateway()
    try:
        gw.emit_settlement_event(
            contract_id='FAIL-01',
            scma_id='SCMA-001',
            gross_payout_cents=1000,
            scma_net_cents=850,
            cfcp_cents=100,
            faep_cents=30
        )
        assert False, 'Conservation assertion did not raise'
    except AssertionError:
        pass

def test_accounting_api_e2e_outbox_and_idempotent_ack():
    client = TestClient(app)
    from app.api.v1.accounting_router import global_accounting_gateway
    global_accounting_gateway.emit_settlement_event(
        contract_id='KX-E2E-99',
        scma_id='SCMA-FOUNDER',
        gross_payout_cents=5000,
        scma_net_cents=4350,
        cfcp_cents=500,
        faep_cents=150
    )
    resp = client.get('/api/v1/accounting/events?since_seq=0')
    assert resp.status_code == 200
    data = resp.json()
    assert data['total_count'] >= 1
    target_evt = data['events'][-1]
    seq_id = target_evt['sequence_id']

    c_bytes = global_accounting_gateway._canonicalize_payload(target_evt['payload'])
    valid_hash = hashlib.sha256(c_bytes).hexdigest()

    bad_ack = client.post('/api/v1/accounting/reconciliation-ack', json={
        'ack_id': 'ACK-BAD-01',
        'sequence_id': seq_id,
        'system_id': 'EXT-GL-01',
        'received_hash': 'bad_hash_token'
    })
    assert bad_ack.status_code == 400

    ok_ack = client.post('/api/v1/accounting/reconciliation-ack', json={
        'ack_id': 'ACK-OK-01',
        'sequence_id': seq_id,
        'system_id': 'EXT-GL-01',
        'received_hash': valid_hash
    })
    assert ok_ack.status_code == 200
    assert ok_ack.json()['status'] == 'SUCCESS'

    dup_ack = client.post('/api/v1/accounting/reconciliation-ack', json={
        'ack_id': 'ACK-OK-01',
        'sequence_id': seq_id,
        'system_id': 'EXT-GL-01',
        'received_hash': valid_hash
    })
    assert dup_ack.status_code == 200
    assert dup_ack.json()['status'] == 'DUPLICATE'
