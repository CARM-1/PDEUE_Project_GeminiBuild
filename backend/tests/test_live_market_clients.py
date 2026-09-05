from app.adapters.live_market_clients import LiveVenueClient
from app.domain.cloud_secrets_broker import CloudSecretsBroker

def test_live_venue_client_lease_integration():
    broker = CloudSecretsBroker()
    client = LiveVenueClient(broker=broker)
    res = client.fetch_kalshi_market('KX-DEMO-TEST', tenant_id='TENANT-LIVE')
    assert res['status'] in ('ONLINE', 'FALLBACK')
    assert 'data' in res

def test_live_venue_polymarket_fetch():
    client = LiveVenueClient()
    res = client.fetch_polymarket_event('EVT-POLY-01')
    assert res['status'] in ('ONLINE', 'FALLBACK')
    assert 'data' in res

def test_live_venue_client_revocation_lockout():
    broker = CloudSecretsBroker()
    client = LiveVenueClient(broker=broker)
    broker.revoke_all_leases(reason='CIRCUIT_BREAKER')
    broker._mock_vault.clear()
    res = client.fetch_kalshi_market('KX-DEMO-LOCK')
    assert res['status'] == 'ERROR'
    assert res['reason'] == 'CREDENTIAL_LEASE_FAILED'
