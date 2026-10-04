"""WP-5D hermetic testnet-sandbox acceptance tests."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.adapters.rate_limiter import VenueRateLimiter
from app.clients.kalshi_client import KalshiClient
from app.clients.polymarket_client import PolymarketClient
from app.domain.scan_worker import AutonomousScanWorker
from app.services.credential_broker import CredentialBroker
from scripts.paper_soak_runner import PaperSoakRunner


def _broker() -> CredentialBroker:
    broker = CredentialBroker()
    broker.register_credential("T-1", "KALSHI", "memory-key-k", "memory-secret-k")
    broker.register_credential("T-1", "POLYMARKET", "memory-key-p", "memory-secret-p")
    return broker


def test_autonomous_worker_uses_ephemeral_leases_and_integer_cent_orders():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "accepted"})

    broker = _broker()
    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient(transport=transport)
    limiter = VenueRateLimiter({
        "KALSHI": {"rate": 10_000, "capacity": 1_000},
        "POLYMARKET": {"rate": 10_000, "capacity": 1_000},
    })
    worker = AutonomousScanWorker(
        execution_mode="TESTNET_SANDBOX", credential_broker=broker,
        kalshi_client=KalshiClient(broker, "T-1", http_client=async_client,
                                   rate_limiter=limiter),
        polymarket_client=PolymarketClient(broker, "T-1", http_client=async_client,
                                           rate_limiter=limiter),
    )
    result = worker.run_single_cycle()
    asyncio.run(async_client.aclose())

    assert result["venue_execution_mode"] == "TESTNET_SANDBOX"
    assert result["status"] == "COMPLETED"
    assert requests
    assert all(
        isinstance(order["limit_price_cents"], int)
        and isinstance(order["notional_cents"], int)
        and isinstance(order["quantity"], int)
        for order in result["dispatched_orders"]
    )
    counts = broker.lifecycle_counts()
    assert counts["acquired"] == counts["revoked"]
    assert counts["active"] == 0


def test_expired_and_revoked_leases_fail_closed_before_transport():
    broker = _broker()
    lease = broker.acquire_lease("T-1", "KALSHI")
    broker.revoke_lease(lease.lease_id)
    with pytest.raises(PermissionError):
        KalshiClient.signing_headers(lease, "POST", "/portfolio/orders", {})

    expired = broker.acquire_lease("T-1", "KALSHI")
    expired.expires_at = datetime.now(timezone.utc) - timedelta(microseconds=1)
    with pytest.raises(PermissionError):
        KalshiClient.signing_headers(expired, "POST", "/portfolio/orders", {})


def test_orders_reject_non_integer_cents_and_sizes():
    broker = _broker()
    kalshi = KalshiClient(broker, "T-1")
    poly = PolymarketClient(broker, "T-1")
    with pytest.raises(TypeError):
        asyncio.run(kalshi.place_order(yes_price=42.5, count=1))
    with pytest.raises(TypeError):
        asyncio.run(poly.create_order(price_cents=42, size=1.5))


def test_http_429_exponential_backoff_preserves_client_state():
    responses = iter((429, 429, 200))
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(next(responses), json={"status": "accepted"})

    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async def exercise() -> dict:
        broker = _broker()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = KalshiClient(broker, "T-1", http_client=http, sleep=sleep)
            return await client.place_order(yes_price=51, count=2)

    assert asyncio.run(exercise())["status"] == "accepted"
    assert calls == 3
    assert len(delays) == 2
    assert delays[1] > delays[0]


def test_ten_request_per_second_token_bucket_burst_ceiling():
    limiter = VenueRateLimiter()
    admitted = [limiter.can_proceed("KALSHI") for _ in range(20)]
    assert sum(admitted) == 10
    assert limiter.warnings_count == 10


def test_qualification_runner_writes_secret_free_acceptance(tmp_path):
    output = tmp_path / "phase5d.json"
    runner = PaperSoakRunner(
        mode=PaperSoakRunner.TESTNET_SANDBOX_QUALIFICATION,
        total_cycles=4, health_export_path=str(output),
    )
    asyncio.run(runner.run_testnet_sandbox_qualification())
    report = output.read_text(encoding="utf-8")
    assert '"mode": "TESTNET_SANDBOX_QUALIFIED"' in report
    assert '"completed_cycles": 4' in report
    assert "qualification-kalshi-secret" not in report
    assert runner.credential_broker.lifecycle_counts()["active"] == 0
