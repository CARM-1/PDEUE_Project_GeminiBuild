import asyncio
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import httpx

from app.clients.kalshi_client import KalshiClient
from app.clients.polymarket_client import PolymarketClient
from app.domain.scan_worker import AutonomousScanWorker
from app.services.credential_broker import CredentialBroker, TenantCredentialLease


def broker_for(venue: str) -> CredentialBroker:
    broker = CredentialBroker()
    broker.register_credential("tenant", venue, "key-id", "in-memory-secret")
    return broker


def test_credential_lease_expiration_and_revocation_scrub_secrets():
    broker = broker_for("KALSHI")
    lease = broker.acquire_lease("tenant", "KALSHI")
    assert lease.is_valid()
    broker.revoke_lease(lease.lease_id)
    assert not lease.is_valid()
    assert lease.api_key == lease.api_secret == ""

    expired = TenantCredentialLease(
        "tenant", "KALSHI", "key", "secret",
        datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert not expired.is_valid()


def test_kalshi_signing_payload_and_429_backoff():
    attempts = 0
    payloads = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        payloads.append(request.content)
        if attempts == 1:
            return httpx.Response(429, request=request)
        return httpx.Response(200, json={"order": {"status": "resting"}}, request=request)

    sleeps = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    broker = broker_for("KALSHI")
    transport = httpx.MockTransport(handler)
    async def scenario():
        async with httpx.AsyncClient(transport=transport) as http:
            client = KalshiClient(broker, "tenant", http_client=http, sleep=fake_sleep)
            return await client.place_order({"ticker": "KX-TEST", "yes_price": 41, "count": 2})

    result = asyncio.run(scenario())
    assert result["order"]["status"] == "resting"
    assert attempts == 2 and len(sleeps) == 1 and payloads[0] == payloads[1]

    lease = broker.acquire_lease("tenant", "KALSHI")
    headers = KalshiClient.signing_headers(lease, "GET", "/markets", timestamp_ms=123)
    expected = hmac.new(b"in-memory-secret", b"123GET/markets", hashlib.sha256).hexdigest()
    assert headers["KALSHI-ACCESS-SIGNATURE"] == expected


def test_polymarket_create_and_cancel_use_mock_transport():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        status = "cancelled" if request.method == "DELETE" else "open"
        return httpx.Response(200, json={"status": status}, request=request)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = PolymarketClient(broker_for("POLYMARKET"), "tenant", http_client=http)
            created = await client.create_order(token_id="123", price_cents=45, size=3, fee_cents=1)
            cancelled = await client.cancel_order("order-1")
            return created, cancelled

    created, cancelled = asyncio.run(scenario())
    assert created["status"] == "open" and cancelled["status"] == "cancelled"
    assert b'"price_cents":45' in requests[0].content
    assert b'"signature":"0x' in requests[0].content
    assert requests[1].url.path.endswith("/order/order-1")


def test_scan_worker_execution_mode_selects_sandbox_clients(monkeypatch):
    monkeypatch.setenv("VENUE_EXECUTION_MODE", "TESTNET_SANDBOX")
    worker = AutonomousScanWorker(credential_broker=CredentialBroker(), tenant_id="tenant")
    assert worker.execution_mode == "TESTNET_SANDBOX"
    assert isinstance(worker.kalshi_client, KalshiClient)
    assert isinstance(worker.poly_client, PolymarketClient)

