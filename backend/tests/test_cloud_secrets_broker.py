from app.domain.cloud_secrets_broker import CloudSecretsBroker
from datetime import datetime, timezone, timedelta

def test_cloud_secrets_leasing_happy_path():
    broker = CloudSecretsBroker(use_mock_aws=True)
    res = broker.lease_venue_credentials(venue='Kalshi', tenant_id='TENANT-ALPHA', ttl_seconds=60)
    assert res['status'] == 'LEASED'
    lease = res['lease']
    assert lease['venue'] == 'KALSHI'
    assert broker.validate_lease(lease['lease_id']) is True

def test_cloud_secrets_leasing_unknown_venue():
    broker = CloudSecretsBroker()
    res = broker.lease_venue_credentials(venue='INVALID_EXCHANGE', tenant_id='TENANT-ALPHA')
    assert res['status'] == 'REJECTED'

def test_cloud_secrets_emergency_revocation():
    broker = CloudSecretsBroker()
    r1 = broker.lease_venue_credentials('Kalshi', 'TENANT-1')
    r2 = broker.lease_venue_credentials('Polymarket', 'TENANT-2')
    l1 = r1['lease']['lease_id']
    l2 = r2['lease']['lease_id']
    assert broker.validate_lease(l1) is True
    assert broker.validate_lease(l2) is True

    revoked_count = broker.revoke_all_leases(reason='EMERGENCY_STOP')
    assert revoked_count == 2
    assert broker.validate_lease(l1) is False
    assert broker.validate_lease(l2) is False
