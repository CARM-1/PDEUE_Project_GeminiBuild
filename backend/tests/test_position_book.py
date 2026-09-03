from app.domain.position_book import PositionBook
from app.domain.global_portfolio_dispatcher import GlobalPortfolioDispatcher
from fastapi.testclient import TestClient
from app.main import app

def test_position_book_fill_accumulation_and_vwap():
    pb = PositionBook()
    pos1 = pb.record_fill('KX-ORD-26', 'KALSHI', 'WEATHER', 'BUY', price=0.10, quantity=100, fill_cost_cents=1000)
    assert pos1['quantity'] == 100
    assert pos1['vwap_price'] == 0.10
    assert pos1['total_cost_cents'] == 1000

    pos2 = pb.record_fill('KX-ORD-26', 'KALSHI', 'WEATHER', 'BUY', price=0.20, quantity=100, fill_cost_cents=2000)
    assert pos2['quantity'] == 200
    assert pos2['vwap_price'] == 0.15
    assert pos2['total_cost_cents'] == 3000

def test_position_book_mtm_revaluation():
    pb = PositionBook()
    pb.record_fill('KX-ORD-26', 'KALSHI', 'WEATHER', 'BUY', price=0.10, quantity=100, fill_cost_cents=1000)
    feed = [{'contract_id': 'KX-ORD-26', 'yes_bid': 0.14, 'yes_ask': 0.16}]
    pb.update_market_prices(feed)
    summary = pb.get_summary()
    assert summary['open_positions_count'] == 1
    pos = summary['positions'][0]
    assert pos['current_mid'] == 0.15
    assert pos['mtm_value_cents'] == 1500
    assert pos['unrealized_pnl_cents'] == 500
    assert pos['roi_pct'] == 50.0

def test_dispatcher_fill_reconciliation():
    pb = PositionBook()
    dispatcher = GlobalPortfolioDispatcher(position_book=pb)
    board = [{'contract_id': 'NFL-01', 'category': 'SPORTS', 'venue': 'KALSHI', 'yes_bid': 0.45, 'yes_ask': 0.50, 'underwriting_spec': {'projected_margin': 7.0, 'target_spread': 3.5}}]
    res = dispatcher.dispatch_cross_category_board('tenant_t', 'acc_t', board)
    assert res['status'] == 'DISPATCHED'
    assert pb.get_summary()['open_positions_count'] == 1

def test_position_api_endpoint():
    client = TestClient(app)
    res = client.get('/api/v1/operator/positions')
    assert res.status_code == 200
    assert 'open_positions_count' in res.json()
