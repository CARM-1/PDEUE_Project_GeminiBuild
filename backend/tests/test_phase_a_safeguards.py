import json
import os
import pytest
import asyncio
from app.adapters.rate_limiter import VenueRateLimiter, TokenBucket
from app.domain.telemetry_sink import TelemetryHealthSink
from app.domain.capital_ledger import CapitalLedger
from app.domain.maker_rebate_adapter import MakerRebateLedgerAdapter

def test_token_bucket_consumption_and_refill():
    bucket = TokenBucket(rate=10.0, capacity=2.0)
    assert bucket.consume(1.0) is True
    assert bucket.consume(1.0) is True
    assert bucket.consume(1.0) is False

def test_venue_rate_limiter_acquire_permit():
    limiter = VenueRateLimiter({'KALSHI': {'rate': 100.0, 'capacity': 2.0}})
    res1 = asyncio.run(limiter.acquire_permit('KALSHI', tokens=1.0))
    res2 = asyncio.run(limiter.acquire_permit('KALSHI', tokens=1.0))
    assert res1 is True
    assert res2 is True

def test_rate_limiter_backoff_and_reset():
    limiter = VenueRateLimiter()
    d1 = limiter.compute_backoff('KALSHI', base_delay=0.5, max_delay=5.0)
    d2 = limiter.compute_backoff('KALSHI', base_delay=0.5, max_delay=5.0)
    assert d2 >= d1
    assert limiter.warnings_count >= 2
    limiter.reset_backoff('KALSHI')
    assert limiter.backoff_counters['KALSHI'] == 0

def test_telemetry_sink_compilation_and_export(tmp_path):
    sink_file = str(tmp_path / 'test_health.json')
    sink = TelemetryHealthSink(export_path=sink_file)
    payload = sink.compile_health_payload(
        ledger_balances={'founder_scma': 10000, 'cfcp': 1500, 'faep': 450},
        maker_stats={'posted': 20, 'filled': 16, 'expired': 4},
        spread_distributions={'WEATHER': 0.02, 'MACRO': 0.03, 'SPORTS': 0.01, 'CRYPTO': 0.04},
        circuit_breaker_status={'is_tripped': False, 'trip_reason': None},
        rate_limiter_warnings=1
    )
    assert payload['status'] == 'HEALTHY'
    assert payload['maker_execution_metrics']['fill_ratio'] == 0.8
    assert payload['balances_cents']['total_equity'] == 11950
    exported = sink.export_health_summary(payload)
    assert os.path.exists(exported)
    with open(exported, 'r', encoding='utf-8') as f:
        loaded = json.load(f)
    assert loaded['maker_execution_metrics']['fill_ratio'] == 0.8

def test_maker_rebate_waterfall_split():
    ledger = CapitalLedger(initial_balance_cents=10000)
    ledger.register_member_account('MEM_ALICE', seed_capital_cents=5000)
    adapter = MakerRebateLedgerAdapter(ledger=ledger)
    event = adapter.process_maker_rebate(
        member_id='MEM_ALICE',
        rebate_cents=100,
        venue='POLYMARKET',
        contract_id='POLY-WTR-01',
        order_id='ORD-REB-1'
    )
    split = event['waterfall_split']
    assert split['founder_pool_cents'] == 3
    assert split['central_family_pool_cents'] == 10
    assert split['member_rebate_cents'] == 87
    assert ledger.members['MEM_ALICE']['balance_cents'] == 5087
    assert ledger.central_family_pool_cents == 10
    assert ledger.founder_pool_cents == 3

def test_maker_rebate_conservation_odd_cents():
    ledger = CapitalLedger(initial_balance_cents=10000)
    ledger.register_member_account('MEM_BOB', seed_capital_cents=5000)
    adapter = MakerRebateLedgerAdapter(ledger=ledger)
    event = adapter.process_maker_rebate(
        member_id='MEM_BOB',
        rebate_cents=33,
        venue='KALSHI',
        contract_id='KX-HIGH-01',
        order_id='ORD-REB-2'
    )
    split = event['waterfall_split']
    assert split['founder_pool_cents'] + split['central_family_pool_cents'] + split['member_rebate_cents'] == 33
    assert ledger.members['MEM_BOB']['balance_cents'] == 5029
