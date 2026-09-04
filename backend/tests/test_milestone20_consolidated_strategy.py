from app.domain.two_tier_risk import TwoTierRiskEnvelope
from app.domain.market_depth import MarketDepthEngine
from app.domain.capital_ledger import CapitalLedger
from app.domain.position_book import PositionBook
from app.domain.settlement_engine import SettlementReconciler

def test_master_convergence_lifecycle():
    ledger = CapitalLedger()
    ledger.register_member_account('MEM-LINEAL-001', seed_capital_cents=10000, max_risk_pct=0.05)
    risk = TwoTierRiskEnvelope(system_max_stake_pct=0.05, kelly_scale=0.25)
    depth = MarketDepthEngine(max_slippage_pct=0.015)
    pb = PositionBook()
    reconciler = SettlementReconciler(position_book=pb, ledger=ledger)

    stake_res = risk.evaluate_stake(total_equity_cents=10000, member_risk_pct=0.05, factor_committed_cents=0, raw_kelly_stake_cents=2000)
    assert stake_res['admitted'] is True
    allocated_cents = stake_res['allocated_stake_cents']
    assert allocated_cents == 500

    book = [{'price': 0.20, 'size': 100.0}]
    depth_res = depth.evaluate_order_depth(book, requested_volume=25.0)
    assert depth_res['executable'] is True

    reserved = ledger.reserve_member_capital('RES-01', 'MEM-LINEAL-001', allocated_cents)
    assert reserved is True

    pb.record_fill('KX-ORD-FAST', 'KALSHI', 'WEATHER', 'BUY_YES', price=0.20, quantity=25, fill_cost_cents=allocated_cents, member_id='MEM-LINEAL-001')
    early_res = reconciler.liquidate_early_position('KX-ORD-FAST', resting_bid=0.92, spread=0.01)
    assert early_res['status'] == 'LIQUIDATED_EARLY'
    wf = early_res['event']['waterfall']
    assert wf['central_family_pool_cents'] > 0
    assert wf['founder_pool_cents'] > 0
    assert wf['member_reinvest_cents'] > 0

    pb.record_fill('KX-ORD-LOSS', 'KALSHI', 'WEATHER', 'BUY_YES', price=0.20, quantity=10, fill_cost_cents=200, member_id='MEM-LINEAL-001')
    loss_res = reconciler.settle_contract('KX-ORD-LOSS', 'NO')
    assert loss_res['status'] == 'SETTLED'
    assert loss_res['event']['waterfall']['central_family_pool_cents'] == 0
    assert loss_res['event']['waterfall']['founder_pool_cents'] == 0
