import pytest
from app.domain.capital_ledger import CapitalLedger
from app.domain.accounting_gateway import AccountingGateway
from app.adapters.platform_yield_adapter import PlatformYieldAdapter

def test_platform_yield_waterfall_and_conservation():
    ledger = CapitalLedger()
    gateway = AccountingGateway()
    adapter = PlatformYieldAdapter(ledger=ledger, gateway=gateway)

    # Register member with $100,000.00 (10,000,000 cents)
    ledger.register_member_account("SCMA-YIELD-01", seed_capital_cents=10000000, max_risk_pct=0.03)

    # Accrue 30 days of yield at 5.00% APY (500 bps)
    res = adapter.accrue_broker_escrow_yield(
        scma_id="SCMA-YIELD-01",
        annual_yield_bps=500,
        elapsed_days=30.0,
        broker_bank_token="EXT-REF-TREASURY-01"
    )

    gross = res["gross_yield_cents"]
    assert gross > 0
    scma = res["scma_net_cents"]
    cfcp = res["cfcp_cents"]
    faep = res["faep_cents"]

    # Invariant: Conservation of exact cents
    assert scma + cfcp + faep == gross
    assert cfcp == (gross * 10) // 100
    assert scma == (gross * 87) // 100

    # Invariant: Ledger balances credited
    mem = ledger.members["SCMA-YIELD-01"]
    assert mem["balance_cents"] == 10000000 + scma
    assert ledger.central_family_pool_cents == cfcp
    assert ledger.founder_pool_cents == faep

def test_ifas_zero_banking_credential_storage():
    adapter = PlatformYieldAdapter()
    adapter.ledger.register_member_account("SCMA-LEAK-TEST", seed_capital_cents=5000000)

    # Direct bank account / routing numbers must fail closed
    with pytest.raises(ValueError, match="Direct banking credentials prohibited"):
        adapter.accrue_broker_escrow_yield(
            scma_id="SCMA-LEAK-TEST",
            broker_bank_token="routing_021000021_acct_987654321"
        )

def test_adr011_signed_event_outbox_integration():
    gateway = AccountingGateway()
    adapter = PlatformYieldAdapter(gateway=gateway)
    adapter.ledger.register_member_account("SCMA-SIG-01", seed_capital_cents=2000000)

    res = adapter.accrue_broker_escrow_yield(
        scma_id="SCMA-SIG-01",
        annual_yield_bps=450,
        elapsed_days=7.0,
        broker_bank_token="EXT-REF-CUSTODY-CHASE"
    )

    outbox_event = res["outbox_event"]
    assert "sequence_id" in outbox_event
    assert outbox_event["status"] in ["EMITTED", "PENDING"]
    
    # Assert tenancy on both adapter return record and signed JSON-LD envelope payload
    assert res["scma_id"] == "SCMA-SIG-01"
    assert outbox_event["payload"]["scma_id"] == "SCMA-SIG-01"

    # Canonical HMAC-SHA256 signature key verification
    sig = outbox_event.get("signature_hmac_sha256") or outbox_event.get("signature")
    assert isinstance(sig, str) and len(sig) == 64
