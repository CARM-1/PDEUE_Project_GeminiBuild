from app.domain.compliance_policy import CompliancePolicyEngine

def test_compliance_approval():
    engine = CompliancePolicyEngine(max_single_event_exposure=20000.0)
    res = engine.evaluate_compliance("tenant_01", venue="KALSHI", jurisdiction="US_IL", proposed_stake=5000.0)
    assert res["admissible"] is True
    assert len(res["policy_flags"]) == 0

def test_compliance_unauthorized_venue():
    engine = CompliancePolicyEngine()
    res = engine.evaluate_compliance("tenant_01", venue="UNREGULATED_DEX", jurisdiction="US_NY", proposed_stake=1000.0)
    assert res["admissible"] is False
    assert "UNAUTHORIZED_VENUE_UNREGULATED_DEX" in res["policy_flags"]

def test_compliance_restricted_jurisdiction():
    engine = CompliancePolicyEngine()
    res = engine.evaluate_compliance("tenant_02", venue="POLYMARKET", jurisdiction="SANCTIONED_ZONE_B", proposed_stake=500.0)
    assert res["admissible"] is False
    assert "RESTRICTED_JURISDICTION_SANCTIONED_ZONE_B" in res["policy_flags"]

def test_compliance_exposure_limit_breach():
    engine = CompliancePolicyEngine(max_single_event_exposure=10000.0)
    res = engine.evaluate_compliance("tenant_03", venue="KALSHI", jurisdiction="US_CA", proposed_stake=15000.0)
    assert res["admissible"] is False
    assert "EXPOSURE_LIMIT_EXCEEDED" in res["policy_flags"]
