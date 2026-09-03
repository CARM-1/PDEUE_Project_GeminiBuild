from app.domain.credential_broker import VenueCredentialBroker
from app.domain.emergency_stop import EmergencyStopExecutor
from app.domain.order_router import OrderRouter

def test_credential_broker_lifecycle():
    broker = VenueCredentialBroker()
    broker.register_credential('tenant_1', 'KALSHI', 'secret-api-key')
    grant = broker.acquire_lease('tenant_1', 'KALSHI', ttl_seconds=60)
    assert grant['status'] == 'GRANTED'
    lease_id = grant['lease']['lease_id']
    assert broker.validate_lease(lease_id) is True
    broker.revoke_lease(lease_id)
    assert broker.validate_lease(lease_id) is False

def test_credential_broker_unknown_venue():
    broker = VenueCredentialBroker()
    grant = broker.acquire_lease('tenant_1', 'UNKNOWN_VENUE')
    assert grant['status'] == 'REJECTED'
    assert grant['reason'] == 'CREDENTIAL_NOT_FOUND'

def test_emergency_stop_halts_router_and_cancels_orders():
    router = OrderRouter()
    executor = EmergencyStopExecutor(order_router=router)
    assert router.emergency_stop is False
    stop_res = executor.trigger_emergency_stop('risk_lead', 'Spike anomaly detected')
    assert stop_res['status'] == 'HALTED'
    assert executor.is_active is True
    assert router.emergency_stop is True

    orders = [{'order_id': 'ORD-101'}, {'order_id': 'ORD-102'}]
    cancelled = executor.cancel_open_orders(orders)
    assert len(cancelled) == 2
    assert cancelled[0]['status'] == 'CANCELLED_BY_EMERGENCY_STOP'

    lift_res = executor.lift_emergency_stop('chief_admin', 'All clear verified')
    assert lift_res['status'] == 'RESUMED'
    assert executor.is_active is False
    assert router.emergency_stop is False
