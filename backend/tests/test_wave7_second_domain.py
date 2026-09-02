from app.domain.economic_engine import EconomicUnderwritingEngine
from app.domain.risk_engine import EventRiskEngine
from app.domain.capital_ledger import CapitalLedger

def test_economic_domain_underwriting():
    engine = EconomicUnderwritingEngine()
    res = engine.evaluate_cpi_event(released_cpi=3.4, target_cpi=3.2)
    assert res["engine_type"] == "ECONOMIC_CPI"
    assert res["calculated_probability"] == 0.9

def test_cross_domain_risk_compatibility():
    econ_engine = EconomicUnderwritingEngine()
    risk_engine = EventRiskEngine()
    ledger = CapitalLedger(initial_balance_cents=1000000)

    eval_res = econ_engine.evaluate_cpi_event(released_cpi=3.1, target_cpi=3.0)
    raw_edge = eval_res["calculated_probability"] - 0.5

    risk_res = risk_engine.evaluate_risk(raw_edge=raw_edge, max_budget_cents=200000)
    assert risk_res["admissible"] is True
    assert ledger.reserve_capital("RES-ECON-01", risk_res["recommended_stake_cents"]) is True
