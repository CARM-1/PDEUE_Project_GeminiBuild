from app.domain.accounting_gateway import AccountingGateway
from app.domain.outbox_dispatcher import OutboxDispatcher

def test_outbox_dispatcher_mock_delivery():
    gw = AccountingGateway()
    gw.emit_settlement_event(
        contract_id='KX-OUTBOX-01',
        scma_id='SCMA-TEST',
        gross_payout_cents=1000,
        scma_net_cents=870,
        cfcp_cents=100,
        faep_cents=30
    )
    dispatcher = OutboxDispatcher(accounting_gw=gw)
    res = dispatcher.dispatch_pending_events(webhook_url=None)
    assert res['status'] == 'COMPLETED'
    assert res['delivered_count'] == 1
    assert gw.event_outbox[0]['status'] == 'DELIVERED'

def test_incident_alert_broadcast():
    dispatcher = OutboxDispatcher()
    alert = dispatcher.broadcast_incident_alert(
        alert_type='CIRCUIT_BREAKER_TRIPPED',
        severity='CRITICAL',
        details={'reason': 'Manual kill-switch triggered by Chief Administrator'}
    )
    assert alert['broadcast_status'] == 'EMITTED'
    assert alert['alert_type'] == 'CIRCUIT_BREAKER_TRIPPED'
    assert len(dispatcher.incident_alerts) == 1
