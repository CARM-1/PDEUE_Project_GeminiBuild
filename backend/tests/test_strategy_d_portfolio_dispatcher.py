from app.domain.global_portfolio_dispatcher import GlobalPortfolioDispatcher
from app.domain.capital_ledger import CapitalLedger
from app.domain.position_book import PositionBook
from app.domain.priority_eviction import PriorityEvictionManager

def test_dispatcher_maker_limit_execution_happy_path():
    dispatcher = GlobalPortfolioDispatcher()
    board = [{
        "contract_id": "KX-CPI-MAKER",
        "category": "MACROECONOMIC",
        "venue": "KALSHI",
        "yes_bid": 0.55,
        "yes_ask": 0.60,
        "underwriting_spec": {
            "threshold": 3.0,
            "evidence": [{"source": "C1", "value": 3.40, "available_at": "2026-09-01T12:00:00Z"}]
        }
    }]
    res = dispatcher.dispatch_cross_category_board(tenant_id="tenant_maker", account_id="acc_maker", board_candidates=board, total_capital=10000.0)
    assert res["status"] == "DISPATCHED"
    assert res["dispatched_count"] == 1
    order = res["dispatched_orders"][0]
    assert order["pricing_mode"] == "MAKER_LIMIT"
    assert order["maker_price"] == 0.56
    assert order["spread_discount"] == 0.04
    assert order["fee_savings"] == 0.006
    assert order["order_intent"]["price"] == 0.56
    assert "RES-" in order["reservation_id"]
    assert order["reservation_id"] in dispatcher.eviction_manager.resting_orders

def test_dispatcher_family_members_maker_limit_execution():
    ledger = CapitalLedger()
    pb = PositionBook()
    eviction = PriorityEvictionManager()
    ledger.register_member_account("MEMBER-MK-01", seed_capital_cents=50000, max_risk_pct=0.05)
    dispatcher = GlobalPortfolioDispatcher(ledger=ledger, position_book=pb, eviction_manager=eviction)
    board = [{
        "contract_id": "WX-ORD-MAKER",
        "category": "WEATHER",
        "venue": "KALSHI",
        "yes_bid": 0.08,
        "yes_ask": 0.12,
        "underwriting_spec": {
            "strike_temp_c": 26.0,
            "ensemble_members": [24.0, 24.5, 25.0, 25.5, 25.0],
            "station_id": "KORD"
        }
    }]
    res = dispatcher.dispatch_for_family_members(board)
    assert res["status"] == "DISPATCHED"
    assert res["members_processed"] == 1
    ord_m = res["dispatched_orders"][0]
    assert ord_m["pricing_mode"] == "MAKER_LIMIT"
    assert ord_m["maker_price"] == 0.09
    assert ord_m["spread_discount"] == 0.03
    assert ord_m["reservation_id"] in eviction.resting_orders
    pos = pb.positions.get("MEMBER-MK-01:WX-ORD-MAKER")
    assert pos is not None
    assert pos["vwap_price"] == 0.09
