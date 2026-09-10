import pytest
from app.domain.global_portfolio_dispatcher import GlobalPortfolioDispatcher
from app.domain.capital_ledger import CapitalLedger
from app.domain.priority_eviction import PriorityEvictionManager

def test_dispatcher_automatic_eviction_on_saturated_board():
    ledger = CapitalLedger(initial_balance_cents=10000)
    eviction_mgr = PriorityEvictionManager(max_concurrent_orders=5, dry_powder_floor_pct=0.40)
    dispatcher = GlobalPortfolioDispatcher(
        ledger=ledger,
        eviction_manager=eviction_mgr,
        max_concurrent_orders=5,
        max_portfolio_exposure_cents=6000
    )

    # Pre-populate 5 low-alpha resting orders to saturate concurrency (5 slots)
    for i in range(1, 6):
        oid = f"RES-RESTING-0{i}"
        ledger.reserve_capital(oid, 300)
        eviction_mgr.register_resting_order(
            order_id=oid,
            ticker=f"TICKER-0{i}",
            domain="WEATHER",
            net_edge=0.04 + (i * 0.01),  # Lowest is 0.05
            stake_cents=300
        )

    assert len(eviction_mgr.resting_orders) == 5

    # New board with candidate carrying massive edge (+84.8%)
    high_alpha_board = [{
        "contract_id": "KX-SUPER-ALPHA",
        "category": "WEATHER",
        "venue": "KALSHI",
        "yes_bid": 0.10,
        "yes_ask": 0.15,
        "hours_to_expiry": 2.0,
        "underwriting_spec": {
            "strike_temp_c": 26.0,
            "ensemble_members": [27.0, 27.5, 28.0, 28.5],
            "station_id": "KORD"
        }
    }]

    res = dispatcher.dispatch_cross_category_board(
        tenant_id="tenant_daemon",
        account_id="acc_daemon",
        board_candidates=high_alpha_board,
        total_capital=100.0
    )

    # Lowest edge order (RES-RESTING-01 with 0.05 edge) should be evicted
    assert res["status"] == "DISPATCHED"
    assert res["dispatched_count"] >= 1
    assert len(eviction_mgr.eviction_history) == 1
    assert eviction_mgr.eviction_history[0]["order_id"] == "RES-RESTING-01"
    assert eviction_mgr.eviction_history[0]["status"] == "CANCELLED_EVICTED"
    assert "RES-RESTING-01" not in eviction_mgr.resting_orders
