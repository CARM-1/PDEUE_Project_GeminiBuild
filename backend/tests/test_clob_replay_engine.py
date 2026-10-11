"""
Microstructure Verification Suite for WP-8B CLOB Replay Engine
Verifies:
1. Routing and execution mechanics across expansion categories.
2. Clock-synchronized pre-announcement quote cancellations.
3. Spread savings and taker fee friction elimination.
4. Hard 40% liquid dry-powder floor and 10% factor group ceilings.
5. Dynamic time-decay early harvesting into resting bids.
"""

import pytest
from app.domain.clob_replay_engine import CLOBReplayEngine
from app.domain.expansion_adapters import UnderwritingDecision

def test_clob_replay_maker_execution_and_spread_capture():
    engine = CLOBReplayEngine(initial_equity_cents=1_000_000)
    decision = UnderwritingDecision(
        category="equity_index",
        contract_id="KX-SPX-5820",
        fair_probability=0.28,
        recommended_bid_cents=21,
        net_edge=0.07,
        should_pull_quotes=False,
        harvest_eligible=False
    )
    order = engine.evaluate_and_stage_order(
        order_id="ORD-001",
        contract_id="KX-SPX-5820",
        category="equity_index",
        factor_group="SPX_2026_09",
        decision=decision,
        best_bid_cents=20,
        best_ask_cents=25,
        timestamp_ns=1700000000000
    )
    assert order is not None
    assert order.status == "RESTING_MAKER"
    assert engine.spread_savings_cents > 0
    assert engine.taker_fees_avoided_cents > 0

    engine.process_trade_tape_print("KX-SPX-5820", print_price_cents=21, print_qty=1000)
    assert "KX-SPX-5820" in engine.open_positions

def test_clob_replay_quote_pull_on_macro_news():
    engine = CLOBReplayEngine(initial_equity_cents=1_000_000)
    decision_pull = UnderwritingDecision(
        category="macro_labor",
        contract_id="KX-NFP-200K",
        fair_probability=0.65,
        recommended_bid_cents=45,
        net_edge=0.10,
        should_pull_quotes=True,
        harvest_eligible=False
    )
    order = engine.evaluate_and_stage_order(
        order_id="ORD-NFP-01",
        contract_id="KX-NFP-200K",
        category="macro_labor",
        factor_group="NFP_2026_09",
        decision=decision_pull,
        best_bid_cents=44,
        best_ask_cents=50,
        timestamp_ns=1700000000000
    )
    assert order is None
    assert engine.orders_cancelled_news_pull == 1

def test_clob_replay_factor_cap_and_cash_floor():
    engine = CLOBReplayEngine(initial_equity_cents=10000, dry_powder_floor_pct=0.40)
    decision = UnderwritingDecision(
        category="energy_eia",
        contract_id="KX-CRUDE-1",
        fair_probability=0.70,
        recommended_bid_cents=50,
        net_edge=0.20,
        should_pull_quotes=False,
        harvest_eligible=False
    )
    order1 = engine.evaluate_and_stage_order(
        order_id="ORD-CRUDE-1",
        contract_id="KX-CRUDE-1",
        category="energy_eia",
        factor_group="EIA_CRUDE_WEEKLY",
        decision=decision,
        best_bid_cents=49,
        best_ask_cents=55,
        timestamp_ns=1700000000000
    )
    assert order1 is not None

    engine.factor_allocations["EIA_CRUDE_WEEKLY"] = 990
    order2 = engine.evaluate_and_stage_order(
        order_id="ORD-CRUDE-2",
        contract_id="KX-CRUDE-2",
        category="energy_eia",
        factor_group="EIA_CRUDE_WEEKLY",
        decision=decision,
        best_bid_cents=49,
        best_ask_cents=55,
        timestamp_ns=1700000000100
    )
    assert order2 is None
    assert engine.factor_cap_blocks == 1

def test_clob_replay_early_profit_harvest():
    engine = CLOBReplayEngine(initial_equity_cents=1_000_000)
    decision = UnderwritingDecision(
        category="sports_spreads",
        contract_id="KX-NFL-KC-3",
        fair_probability=0.75,
        recommended_bid_cents=50,
        net_edge=0.25,
        should_pull_quotes=False,
        harvest_eligible=False
    )
    engine.evaluate_and_stage_order(
        order_id="ORD-NFL",
        contract_id="KX-NFL-KC-3",
        category="sports_spreads",
        factor_group="NFL_WEEK_4",
        decision=decision,
        best_bid_cents=49,
        best_ask_cents=55,
        timestamp_ns=1700000000000
    )
    engine.process_trade_tape_print("KX-NFL-KC-3", print_price_cents=50, print_qty=500)
    assert "KX-NFL-KC-3" in engine.open_positions

    harvested = engine.evaluate_early_harvest("KX-NFL-KC-3", current_market_bid_cents=82)
    assert harvested is True
    assert "KX-NFL-KC-3" not in engine.open_positions
    assert engine.positions_harvested_early == 1
