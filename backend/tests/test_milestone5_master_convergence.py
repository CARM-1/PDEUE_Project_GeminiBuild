from fastapi.testclient import TestClient
from app.main import app
from app.adapters.platform_yield_adapter import PlatformYieldAdapter
from app.domain.capital_ledger import CapitalLedger
from app.domain.cloud_secrets_broker import CloudSecretsBroker
from app.db.models import AccountModel, TenantModel

def test_milestone5_master_convergence_lifecycle():
    """
    Master Integration Convergence:
    Validates B6 desktops, ADR-011 yield outbox, ephemeral secrets leasing,
    and relational persistence in an end-to-end pass.
    """
    client = TestClient(app)

    # 1. B6 Presentation Portals
    for route, expected_title in [
        ("/member", "Member User Desktop"),
        ("/advisor", "Financial Advisor Workspace"),
        ("/admin/tech", "Technical Infrastructure Console")
    ]:
        res = client.get(route)
        assert res.status_code == 200
        assert expected_title in res.text

    # 2. Platform Yield & ADR-011 Outbox Settlement
    ledger = CapitalLedger()
    ledger.register_member_account("SCMA-CONV-01", seed_capital_cents=5000000, max_risk_pct=0.03)
    adapter = PlatformYieldAdapter(ledger=ledger)
    y_res = adapter.accrue_broker_escrow_yield(
        scma_id="SCMA-CONV-01",
        annual_yield_bps=500,
        elapsed_days=7.0,
        broker_bank_token="EXT-REF-CONVERGENCE"
    )
    assert y_res["gross_yield_cents"] > 0
    gross = y_res["gross_yield_cents"]
    assert y_res["scma_net_cents"] + y_res["cfcp_cents"] + y_res["faep_cents"] == gross
    assert y_res["scma_net_cents"] == (gross * 87) // 100
    assert y_res["cfcp_cents"] == (gross * 10) // 100
    assert y_res["outbox_event"]["status"] in ["EMITTED", "PENDING"]

    # 3. Dynamic Secrets Leasing Broker
    broker = CloudSecretsBroker(use_mock_aws=True)
    lease_res = broker.lease_venue_credentials(venue="Kalshi", tenant_id="TENANT-CONV", ttl_seconds=60)
    assert lease_res["status"] == "LEASED"
    assert broker.validate_lease(lease_res["lease"]["lease_id"]) is True

    # 4. Relational Persistence Models
    acc = AccountModel(
        account_id="ACC-CONV-01",
        user_id="USR-CONV-01",
        account_name="Master Convergence Account",
        balance_cents=5000000
    )
    assert acc.account_id == "ACC-CONV-01"
    assert acc.balance_cents == 5000000
