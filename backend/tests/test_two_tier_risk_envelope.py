from app.domain.two_tier_risk import TwoTierRiskEnvelope

def test_system_cap_invariant():
    risk = TwoTierRiskEnvelope(system_max_stake_pct=0.05, kelly_scale=0.25)
    res = risk.evaluate_stake(total_equity_cents=10000, member_risk_pct=0.05, factor_committed_cents=0, raw_kelly_stake_cents=4000)
    assert res['admitted'] is True
    assert res['allocated_stake_cents'] <= 500
    assert res['allocated_stake_cents'] == 500

def test_downward_only_member_discretion():
    risk = TwoTierRiskEnvelope(system_max_stake_pct=0.05, kelly_scale=0.25)
    res_down = risk.evaluate_stake(total_equity_cents=10000, member_risk_pct=0.02, factor_committed_cents=0, raw_kelly_stake_cents=4000)
    assert res_down['admitted'] is True
    assert res_down['allocated_stake_cents'] == 200

    res_up = risk.evaluate_stake(total_equity_cents=10000, member_risk_pct=0.25, factor_committed_cents=0, raw_kelly_stake_cents=4000)
    assert res_up['admitted'] is True
    assert res_up['allocated_stake_cents'] == 500
    assert res_up['effective_stake_pct'] == 0.05

def test_factor_concentration_cap():
    risk = TwoTierRiskEnvelope(system_max_stake_pct=0.05, max_factor_exposure_pct=0.10)
    res = risk.evaluate_stake(total_equity_cents=10000, member_risk_pct=0.05, factor_committed_cents=800, raw_kelly_stake_cents=4000)
    assert res['admitted'] is True
    assert res['allocated_stake_cents'] == 200

    res_blocked = risk.evaluate_stake(total_equity_cents=10000, member_risk_pct=0.05, factor_committed_cents=1000, raw_kelly_stake_cents=4000)
    assert res_blocked['admitted'] is False
    assert res_blocked['reason'] == 'FACTOR_CONCENTRATION_EXCEEDED'
