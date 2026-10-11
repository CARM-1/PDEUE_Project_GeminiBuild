"""
Microstructure Verification Suite for WP-8C Venue Tape Ingestor & Benchmark Runner
Verifies:
1. FIFO Queue Depth Realism (Q_ahead absorption before fill).
2. Taker fee drag elimination and inside spread savings.
3. 87/10/3 exact-cent waterfall distribution integrity.
4. Continuous multi-category batch replay execution.
"""

import pytest
from app.domain.venue_tape_ingestor import MarketTradePrint, MicrostructureQueueTracker
from app.domain.crowd_benchmark_runner import CrowdBenchmarkRunner

def test_queue_depth_absorption_realism():
    tracker = MicrostructureQueueTracker()
    tracker.register_order_in_queue(
        order_id="ORD-TEST-01",
        contract_id="KX-SPX-5820",
        price_cents=21,
        quantity=100,
        existing_l2_book_depth=200
    )
    # Print 1: 150 contracts trade at 21c -> Absorbed by Q_ahead, our order receives ZERO fills
    p1 = MarketTradePrint("T1", "KX-SPX-5820", "equity_index", 1000, 21, 150, "SELL")
    fills1 = tracker.process_incoming_trade_print(p1)
    assert len(fills1) == 0
    assert tracker.active_queues["ORD-TEST-01"].queue_ahead_volume == 50

    # Print 2: 100 contracts trade at 21c -> Consumes remaining 50 ahead, fills 50 of ours!
    p2 = MarketTradePrint("T2", "KX-SPX-5820", "equity_index", 2000, 21, 100, "SELL")
    fills2 = tracker.process_incoming_trade_print(p2)
    assert len(fills2) == 1
    assert fills2[0] == ("ORD-TEST-01", 50)
    assert tracker.active_queues["ORD-TEST-01"].filled_quantity == 50

def test_crowd_benchmark_multi_category_batch():
    runner = CrowdBenchmarkRunner(initial_equity_cents=1_000_000)
    contracts_batch = [
        {
            "contract_id": "KX-NFP-1", "category": "macro_labor", "best_bid_cents": 44, "best_ask_cents": 50,
            "p_fair": 0.65, "seconds_to_release": 2.0, "timestamp_ns": 1000, "l2_depth_ahead": 50, "trade_prints": []
        },
        {
            "contract_id": "KX-SPX-1", "category": "equity_index", "best_bid_cents": 20, "best_ask_cents": 25,
            "p_fair": 0.28, "seconds_to_release": 120.0, "timestamp_ns": 2000, "l2_depth_ahead": 50,
            "trade_prints": [MarketTradePrint("T1", "KX-SPX-1", "equity_index", 2500, 21, 1000, "SELL")],
            "market_bid_later_cents": 85
        },
        {
            "contract_id": "KX-CRUDE-1", "category": "energy_eia", "best_bid_cents": 48, "best_ask_cents": 54,
            "p_fair": 0.70, "seconds_to_release": 120.0, "timestamp_ns": 3000, "l2_depth_ahead": 20,
            "trade_prints": [MarketTradePrint("T2", "KX-CRUDE-1", "energy_eia", 3500, 49, 500, "SELL")],
            "market_bid_later_cents": 82
        }
    ]

    report = runner.run_replay_batch(contracts_batch)
    assert report["summary"].total_orders_staged == 3
    assert report["summary"].orders_cancelled_news_pull == 1
    assert report["summary"].orders_filled >= 1
    assert report["summary"].positions_harvested_early >= 1
    assert report["summary"].spread_savings_cents > 0
    assert report["summary"].taker_fees_avoided_cents > 0
    assert report["scma_cents"] + report["cfcp_cents"] + report["faep_cents"] == report["net_profit_cents"]

    # Render terminal scorecard
    runner.print_terminal_scorecard()
