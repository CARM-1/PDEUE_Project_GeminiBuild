import pytest
from app.domain.scan_worker import AutonomousScanWorker
from app.domain.capital_ledger import CapitalLedger
from app.domain.cloud_secrets_broker import CloudSecretsBroker
from app.domain.two_tier_risk import TwoTierRiskEnvelope
from app.adapters.platform_yield_adapter import PlatformYieldAdapter

def test_milestone3_autonomous_loop_single_cycle():
    """Validates AutonomousScanWorker single-cycle scan and dispatch against baseline contract."""
    worker = AutonomousScanWorker()
    cycle_res = worker.run_single_cycle()
    assert cycle_res["cycle_number"] >= 1
    assert cycle_res["contracts_scanned"] >= 1
    assert worker.stats["cycles_completed"] >= 1
    assert worker.stats["total_contracts_scanned"] >= 1

def test_milestone3_exchange_credential_lease_lifecycle():
    """Validates ephemeral venue credential leasing and unknown venue rejection."""
    broker = CloudSecretsBroker(use_mock_aws=True)

    # 1. Successful venue credential lease
    res = broker.lease_venue_credentials(venue="Kalshi", tenant_id="TENANT-M3", ttl_seconds=60)
    assert res["status"] == "LEASED"
    lease = res["lease"]
    assert lease["venue"] == "KALSHI"
    assert broker.validate_lease(lease["lease_id"]) is True

    # 2. Unknown venue rejection fails closed
    bad_res = broker.lease_venue_credentials(venue="INVALID_EXCHANGE", tenant_id="TENANT-M3")
    assert bad_res["status"] == "REJECTED"

def test_milestone3_yield_and_risk_envelope_coordination():
    """Validates coordination between two-tier risk allocation and idle cash yield accrual."""
    # 1. Verify two-tier risk envelope capping (5% system max, 3% member risk dial)
    risk = TwoTierRiskEnvelope(system_max_stake_pct=0.05, kelly_scale=0.25)
    res_stake = risk.evaluate_stake(
        total_equity_cents=5000000,
        member_risk_pct=0.03,
        factor_committed_cents=0,
        raw_kelly_stake_cents=200000
    )
    assert res_stake["admitted"] is True
    # Member dial cap is 3% of 5,000,000 = 150,000 cents ($1,500.00)
    assert res_stake["allocated_stake_cents"] <= 150000

    # 2. Accrue idle cash yield on remaining uncommitted balance
    ledger = CapitalLedger()
    ledger.register_member_account("SCMA-M3-01", seed_capital_cents=5000000, max_risk_pct=0.03)
    yield_adapter = PlatformYieldAdapter(ledger=ledger)
    yield_res = yield_adapter.accrue_broker_escrow_yield(
        scma_id="SCMA-M3-01",
        annual_yield_bps=475,
        elapsed_days=14.0,
        broker_bank_token="EXT-REF-TREASURY-M3"
    )
    assert yield_res["gross_yield_cents"] > 0
    assert yield_res["scma_net_cents"] == (yield_res["gross_yield_cents"] * 87) // 100
    assert yield_res["cfcp_cents"] == (yield_res["gross_yield_cents"] * 10) // 100
    assert yield_res["faep_cents"] == yield_res["gross_yield_cents"] - yield_res["scma_net_cents"] - yield_res["cfcp_cents"]
