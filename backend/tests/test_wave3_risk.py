from app.domain.risk_engine import EventRiskEngine
from app.domain.capital_ledger import CapitalLedger

def test_risk_evaluation():
    engine = EventRiskEngine()
    res = engine.evaluate_risk(raw_edge=0.18, max_budget_cents=100000)
    assert res["admissible"] is True
    assert res["recommended_stake_cents"] == 18000

def test_capital_ledger_reservation():
    ledger = CapitalLedger(initial_balance_cents=500000)
    assert ledger.reserve_capital("RES-001", 18000) is True
    assert ledger.balance_cents == 482000
    assert ledger.reserve_capital("RES-002", 600000) is False
