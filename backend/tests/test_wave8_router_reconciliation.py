from app.domain.order_router import OrderRouter
from app.domain.reconciliation_engine import ReconciliationEngine

def test_order_router_success():
    router = OrderRouter()
    validated_order = {'is_valid': True, 'order_id': 'ORD-TEST-001', 'contract_id': 'KX-WEATHER-HIGH-75', 'side': 'BUY', 'price': 0.65, 'quantity': 100, 'idempotency_key': 'IDEM-W8-001'}
    res = router.route_order(validated_order, venue='KALSHI')
    assert res['status'] == 'SUCCESS'
    assert res['order_id'] == 'ORD-TEST-001'
    assert 'ORD-TEST-001' in router.routed_orders

def test_order_router_rejection_invalid_order():
    router = OrderRouter()
    res = router.route_order({'is_valid': False}, venue='KALSHI')
    assert res['status'] == 'REJECTED'
    assert res['reason'] == 'INVALID_PRE_TRADE_ORDER'

def test_order_router_emergency_stop():
    router = OrderRouter()
    router.set_emergency_stop(True)
    res = router.route_order({'is_valid': True}, venue='KALSHI')
    assert res['status'] == 'REJECTED'
    assert res['reason'] == 'EMERGENCY_STOP_ACTIVE'

def test_reconciliation_clean_fill():
    engine = ReconciliationEngine()
    internal = {'order_id': 'ORD-REC-01', 'contract_id': 'CT-CPI-26', 'side': 'BUY', 'quantity': 50, 'price': 0.40}
    engine.record_fill(order_id='ORD-REC-01', fill_price=0.40, fill_quantity=50)
    venue_report = {'contract_id': 'CT-CPI-26', 'side': 'BUY', 'filled_quantity': 50, 'status': 'FILLED'}
    rec = engine.reconcile(internal, venue_report)
    assert rec['is_reconciled'] is True
    assert rec['vwap'] == 0.40
    assert len(rec['discrepancies']) == 0

def test_reconciliation_partial_fills_and_vwap():
    engine = ReconciliationEngine()
    internal = {'order_id': 'ORD-REC-02', 'contract_id': 'CT-CPI-26', 'side': 'BUY', 'quantity': 100, 'price': 0.50}
    engine.record_fill(order_id='ORD-REC-02', fill_price=0.48, fill_quantity=40)
    engine.record_fill(order_id='ORD-REC-02', fill_price=0.52, fill_quantity=60)
    venue_report = {'contract_id': 'CT-CPI-26', 'side': 'BUY', 'filled_quantity': 100, 'status': 'FILLED'}
    rec = engine.reconcile(internal, venue_report)
    assert rec['is_reconciled'] is True
    assert rec['vwap'] == 0.504
    assert rec['remaining_quantity'] == 0

def test_reconciliation_mismatch_and_overfill():
    engine = ReconciliationEngine()
    internal = {'order_id': 'ORD-REC-03', 'contract_id': 'CT-CPI-26', 'side': 'BUY', 'quantity': 50, 'price': 0.50}
    bad_venue = {'contract_id': 'CT-MISMATCH', 'side': 'SELL', 'filled_quantity': 60, 'status': 'FILLED'}
    rec = engine.reconcile(internal, bad_venue)
    assert rec['is_reconciled'] is False
    assert 'CONTRACT_ID_MISMATCH' in rec['discrepancies']
    assert 'SIDE_MISMATCH' in rec['discrepancies']
    assert 'OVERFILL_DETECTED' in rec['discrepancies']
