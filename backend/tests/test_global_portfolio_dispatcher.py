from app.domain.global_portfolio_dispatcher import GlobalPortfolioDispatcher
from app.db.session import Base, engine, SessionLocal
from app.db.models import DecisionPacketRecordModel, OrderRecordModel

def test_portfolio_dispatcher_multi_domain_happy_path():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    dispatcher = GlobalPortfolioDispatcher(db_session=db)
    board = [
        {'contract_id': 'KX-ORD-26', 'category': 'WEATHER', 'venue': 'KALSHI', 'yes_bid': 0.08, 'yes_ask': 0.12, 'underwriting_spec': {'strike_temp_c': 26.0, 'ensemble_members': [24.0, 24.5, 25.0, 25.5, 25.0], 'station_id': 'KORD'}},
        {'contract_id': 'KX-CPI-3.0', 'category': 'MACROECONOMIC', 'venue': 'KALSHI', 'yes_bid': 0.55, 'yes_ask': 0.60, 'underwriting_spec': {'threshold': 3.0, 'evidence': [{'source': 'C1', 'value': 3.40, 'available_at': '2026-09-01T12:00:00Z'}, {'source': 'C2', 'value': 3.50, 'available_at': '2026-09-02T12:00:00Z'}]}}
    ]
    res = dispatcher.dispatch_cross_category_board(tenant_id='tenant_global_01', account_id='acc_global_01', board_candidates=board, total_capital=10000.0)
    assert res['status'] == 'DISPATCHED'
    assert res['dispatched_count'] == 2
    assert res['total_allocated_cents'] > 0
    assert db.query(DecisionPacketRecordModel).filter_by(tenant_id='tenant_global_01').count() == 2
    assert db.query(OrderRecordModel).filter_by(tenant_id='tenant_global_01').count() == 2
    db.close()

def test_portfolio_dispatcher_enforces_exposure_cap():
    dispatcher = GlobalPortfolioDispatcher(max_portfolio_exposure_cents=10000)
    board = [
        {'contract_id': 'KX-CPI-3.0', 'category': 'MACROECONOMIC', 'venue': 'KALSHI', 'yes_bid': 0.55, 'yes_ask': 0.60, 'underwriting_spec': {'threshold': 3.0, 'evidence': [{'source': 'C1', 'value': 3.40, 'available_at': '2026-09-01T12:00:00Z'}]}}
    ]
    res = dispatcher.dispatch_cross_category_board(tenant_id='tenant_cap', account_id='acc_cap', board_candidates=board, total_capital=100000.0)
    assert res['total_allocated_cents'] <= 10000

def test_portfolio_dispatcher_abstains_on_zero_edge():
    dispatcher = GlobalPortfolioDispatcher()
    board = [{'contract_id': 'KX-EFFICIENT', 'category': 'WEATHER', 'venue': 'KALSHI', 'yes_bid': 0.48, 'yes_ask': 0.52, 'underwriting_spec': {'strike_temp_c': 20.0, 'ensemble_members': [20.0, 20.0, 20.0], 'station_id': None}}]
    res = dispatcher.dispatch_cross_category_board(tenant_id='tenant_zero', account_id='acc_zero', board_candidates=board, total_capital=10000.0)
    assert res['status'] == 'ABSTAINED'
    assert res['dispatched_count'] == 0
