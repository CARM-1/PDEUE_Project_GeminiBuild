import pytest
from app.domain.identity_governance import IdentityGovernanceEngine

def test_role_authorization_and_isolation():
    gov = IdentityGovernanceEngine()
    gov.register_principal("usr_ops", "tenant_a", ["OPERATOR"])
    gov.register_principal("usr_auditor", "tenant_a", ["AUDITOR"])

    # Authorized
    res = gov.authorize_action("usr_ops", "tenant_a", "START_SESSION")
    assert res["authorized"] is True
    assert res["reason"] == "AUTHORIZED"

    # Unauthorized action for role
    res_deny = gov.authorize_action("usr_auditor", "tenant_a", "START_SESSION")
    assert res_deny["authorized"] is False
    assert "INSUFFICIENT_PERMISSIONS" in res_deny["reason"]

    # Cross-tenant access denied
    res_cross = gov.authorize_action("usr_ops", "tenant_b", "VIEW_AUDIT")
    assert res_cross["authorized"] is False
    assert res_cross["reason"] == "CROSS_TENANT_ACCESS_DENIED"

def test_secrets_governance_and_leasing():
    gov = IdentityGovernanceEngine()
    gov.register_principal("admin_01", "tenant_a", ["CHIEF_ADMIN"])
    gov.register_principal("trader_01", "tenant_a", ["OPERATOR"])
    gov.register_secret_reference("tenant_a", "KALSHI_API_KEY", "aws:secretsmanager:us-east-1:kalshi_key_01")

    # Chief Admin can lease
    lease = gov.lease_secret_reference("admin_01", "tenant_a", "KALSHI_API_KEY")
    assert lease["success"] is True
    assert lease["vault_uri"] == "aws:secretsmanager:us-east-1:kalshi_key_01"

    # Trader/Operator cannot lease
    lease_deny = gov.lease_secret_reference("trader_01", "tenant_a", "KALSHI_API_KEY")
    assert lease_deny["success"] is False
    assert "INSUFFICIENT_PERMISSIONS" in lease_deny["reason"]
