from app.domain.global_portfolio_dispatcher import GlobalPortfolioDispatcher
from app.domain.capital_ledger import CapitalLedger
from app.domain.position_book import PositionBook
from app.domain.settlement_engine import SettlementReconciler
from app.domain.scan_worker import AutonomousScanWorker

def test_multi_member_proportional_dispatch():
    ledger = CapitalLedger()
    pb = PositionBook()
    ledger.register_member_account('MEMBER-G1-001', seed_capital_cents=10000, max_risk_pct=0.02)
    ledger.register_member_account('MEMBER-G2-002', seed_capital_cents=50000, max_risk_pct=0.05)
    dispatcher = GlobalPortfolioDispatcher(ledger=ledger, position_book=pb)
    board = [{'contract_id': 'WX-ORD-26', 'category': 'WEATHER', 'venue': 'KALSHI', 'yes_bid': 0.08, 'yes_ask': 0.12, 'underwriting_spec': {'strike_temp_c': 26.0, 'ensemble_members': [24.0, 24.5, 25.0, 25.5, 25.0], 'station_id': 'KORD'}}]
    res = dispatcher.dispatch_for_family_members(board)
    assert res['status'] == 'DISPATCHED'
    assert res['members_processed'] == 2
    assert len(res['dispatched_orders']) == 2
    orders_by_member = {o['member_id']: o for o in res['dispatched_orders']}
    ord_g1 = orders_by_member['MEMBER-G1-001']
    ord_g2 = orders_by_member['MEMBER-G2-002']
    assert ord_g1['cost_cents'] <= 200
    assert ord_g2['cost_cents'] <= 2500
    assert ord_g2['cost_cents'] > ord_g1['cost_cents']

def test_multi_member_settlement_waterfall_and_isolation():
    ledger = CapitalLedger()
    pb = PositionBook()
    ledger.register_member_account('MEMBER-G1-001', seed_capital_cents=10000, max_risk_pct=0.05)
    pb.record_fill('KX-ORD-TEST', 'KALSHI', 'WEATHER', 'BUY_YES', price=0.20, quantity=10, fill_cost_cents=200, member_id='MEMBER-G1-001')
    reconciler = SettlementReconciler(position_book=pb, ledger=ledger)
    res = reconciler.settle_contract('KX-ORD-TEST', 'YES', member_id='MEMBER-G1-001')
    assert res['status'] == 'SETTLED'
    wf = res['event']['waterfall']
    assert wf['member_reinvest_cents'] > 0
    assert wf['central_family_pool_cents'] > 0
    assert wf['founder_pool_cents'] > 0

def test_autonomous_scan_worker_multi_member_cycle():
    ledger = CapitalLedger()
    pb = PositionBook()
    ledger.register_member_account('MEMBER-AUTONOMOUS', seed_capital_cents=10000, max_risk_pct=0.05)
    worker = AutonomousScanWorker(ledger=ledger, position_book=pb)
    res = worker.run_single_cycle()
    assert res['status'] in ('DISPATCHED', 'COMPLETED')
    assert worker.cycles_completed == 1
