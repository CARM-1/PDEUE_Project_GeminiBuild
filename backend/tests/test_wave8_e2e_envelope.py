from app.domain.execution_coordinator import ExecutionEnvelopeCoordinator

def test_full_execution_envelope_happy_path():
    coordinator = ExecutionEnvelopeCoordinator(mode='PAPER')
    coordinator.credential_broker.register_credential('tenant_alpha', 'KALSHI', 'secret-kalshi-token')
    lease = coordinator.credential_broker.acquire_lease('tenant_alpha', 'KALSHI', ttl_seconds=300)
    assert lease['status'] == 'GRANTED'
    assert coordinator.credential_broker.validate_lease(lease['lease']['lease_id']) is True

    order_intent = {
        'decision_packet_id': 'PKT-E2E-001',
        'contract_id': 'KX-CPI-ABOVE-3.2',
        'side': 'BUY',
        'price': 0.55,
        'quantity': 100,
        'total_cost_cents': 5500,
        'idempotency_key': 'IDEM-E2E-001'
    }
    reservation = {'reserved': True, 'reserved_cents': 6000}
    exec_res = coordinator.execute_order_lifecycle(
        tenant_id='tenant_alpha',
        account_id='acc_01',
        venue='KALSHI',
        order_intent=order_intent,
        reservation=reservation
    )
    assert exec_res['success'] is True
    assert exec_res['stage'] == 'ROUTED'
    order_id = exec_res['order_id']

    coordinator.reconciliation_engine.record_fill(order_id=order_id, fill_price=0.54, fill_quantity=40)
    coordinator.reconciliation_engine.record_fill(order_id=order_id, fill_price=0.56, fill_quantity=60)
    venue_report = {'contract_id': 'KX-CPI-ABOVE-3.2', 'side': 'BUY', 'filled_quantity': 100, 'status': 'FILLED'}
    internal_order = exec_res['routed_payload']
    rec = coordinator.reconciliation_engine.reconcile(internal_order, venue_report)
    assert rec['is_reconciled'] is True
    assert rec['cumulative_filled_quantity'] == 100
    assert rec['vwap'] == 0.552

    pos = coordinator.position_service.update_from_fill(
        tenant_id='tenant_alpha',
        account_id='acc_01',
        contract_id='KX-CPI-ABOVE-3.2',
        side='BUY',
        fill_price=rec['vwap'],
        fill_quantity=100
    )
    assert pos['quantity'] == 100
    assert pos['cost_basis_cents'] == 5520

    mtm = coordinator.position_service.mark_to_market('tenant_alpha', 'acc_01', 'KX-CPI-ABOVE-3.2', market_price=0.70)
    assert mtm['current_value_cents'] == 7000
    assert mtm['unrealized_pnl_cents'] == 1480

    settle_res = coordinator.settlement_interface.settle_position(
        tenant_id='tenant_alpha',
        account_id='acc_01',
        contract_id='KX-CPI-ABOVE-3.2',
        position=pos,
        outcome='YES',
        settlement_fee_cents=50
    )
    assert settle_res['status'] == 'SUCCESS'
    assert settle_res['record']['gross_payout_cents'] == 10000
    assert settle_res['record']['net_payout_cents'] == 9950
    assert settle_res['record']['realized_pnl_cents'] == 4430

def test_execution_coordinator_fails_closed_on_emergency_stop():
    coordinator = ExecutionEnvelopeCoordinator(mode='PAPER')
    coordinator.emergency_stop.trigger_emergency_stop('risk_operator', 'Market dislocation detected')
    order_intent = {'decision_packet_id': 'PKT-002', 'contract_id': 'KX-WX-01', 'side': 'BUY', 'price': 0.40, 'quantity': 10, 'total_cost_cents': 400, 'idempotency_key': 'KEY-002'}
    res = coordinator.execute_order_lifecycle('tenant_alpha', 'acc_01', 'KALSHI', order_intent, {'reserved': True, 'reserved_cents': 500})
    assert res['success'] is False
    assert res['stage'] == 'EMERGENCY_STOP'
    assert res['reason'] == 'EMERGENCY_STOP_ACTIVE'

def test_execution_coordinator_reservation_deficit():
    coordinator = ExecutionEnvelopeCoordinator(mode='PAPER')
    order_intent = {'decision_packet_id': 'PKT-003', 'contract_id': 'KX-WX-02', 'side': 'BUY', 'price': 0.50, 'quantity': 50, 'total_cost_cents': 2500, 'idempotency_key': 'KEY-003'}
    res = coordinator.execute_order_lifecycle('tenant_alpha', 'acc_01', 'KALSHI', order_intent, {'reserved': True, 'reserved_cents': 1000})
    assert res['success'] is False
    assert res['stage'] == 'POLICY_GATE'
    assert res['reason'] == 'RESERVATION_EXCEEDED'

def test_execution_coordinator_invalid_pretrade_order():
    coordinator = ExecutionEnvelopeCoordinator(mode='PAPER')
    bad_intent = {'decision_packet_id': 'PKT-004', 'contract_id': 'KX-WX-03', 'side': 'BUY', 'price': 1.50, 'quantity': 10, 'total_cost_cents': 1500, 'idempotency_key': 'KEY-004'}
    res = coordinator.execute_order_lifecycle('tenant_alpha', 'acc_01', 'KALSHI', bad_intent, {'reserved': True, 'reserved_cents': 2000})
    assert res['success'] is False
    assert res['stage'] == 'PRE_TRADE_VALIDATION'
    assert res['reason'] == 'PRICE_OUT_OF_BOUNDS'
