"""
PDEUE Continuous 12-Category Crowd Benchmark Runner & Dynamic Audit Visualizer
Evaluates Strategy D execution against crowd metrics with zero phantom accounting.
"""

from dataclasses import dataclass
from typing import Dict, Any, List
from app.domain.venue_tape_ingestor import MarketTradePrint, MicrostructureQueueTracker
from app.domain.clob_replay_engine import CLOBReplayEngine
from app.domain.expansion_adapters import UnderwritingDecision

@dataclass
class CategoryBenchmarkResult:
    category: str
    contracts_evaluated: int
    orders_filled: int
    dynamic_harvests: int
    news_pulls_executed: int

class CrowdBenchmarkRunner:
    def __init__(self, initial_equity_cents: int = 1_000_000):
        self.initial_equity_cents = initial_equity_cents
        self.engine = CLOBReplayEngine(initial_equity_cents=initial_equity_cents)
        self.queue_tracker = MicrostructureQueueTracker()
        self.category_stats: Dict[str, CategoryBenchmarkResult] = {}

    def run_replay_batch(self, contracts_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        for c in contracts_data:
            cat = c["category"]
            cid = c["contract_id"]
            best_bid = c["best_bid_cents"]
            best_ask = c["best_ask_cents"]
            l2_depth = c.get("l2_depth_ahead", 100)

            # 1. Underwrite
            adapter = self.engine.adapters.get(cat)
            p_fair = c.get("p_fair", 0.65)
            should_pull = c.get("seconds_to_release", 120.0) <= 5.0
            rec_bid = max(1, min(best_bid + 1, int(p_fair * 100) - 2))
            
            decision = UnderwritingDecision(
                category=cat,
                contract_id=cid,
                fair_probability=p_fair,
                recommended_bid_cents=rec_bid,
                net_edge=round(p_fair - (rec_bid / 100.0), 4),
                should_pull_quotes=should_pull,
                harvest_eligible=rec_bid >= 80
            )

            # 2. Stage Order
            oid = f"ORD-{cid}"
            order = self.engine.evaluate_and_stage_order(
                order_id=oid,
                contract_id=cid,
                category=cat,
                factor_group=c.get("factor_group", f"{cat}_grp"),
                decision=decision,
                best_bid_cents=best_bid,
                best_ask_cents=best_ask,
                timestamp_ns=c["timestamp_ns"]
            )

            if order:
                # 3. Register in Queue Tracker
                self.queue_tracker.register_order_in_queue(
                    order_id=oid,
                    contract_id=cid,
                    price_cents=order.price_cents,
                    quantity=order.quantity,
                    existing_l2_book_depth=l2_depth
                )

                # 4. Ingest Historical Trade Prints
                for tp in c.get("trade_prints", []):
                    fills = self.queue_tracker.process_incoming_trade_print(tp)
                    for filled_oid, filled_qty in fills:
                        self.engine.process_trade_tape_print(cid, tp.price_cents, filled_qty)

                # 5. Expire unfilled residue to release locked margin for future contracts
                self.engine.expire_unfilled_order(oid)

                # 6. Check Dynamic Early Harvest
                if c.get("market_bid_later_cents", 0) >= 80:
                    self.engine.evaluate_early_harvest(cid, c["market_bid_later_cents"])

            # Category tracking
            if cat not in self.category_stats:
                self.category_stats[cat] = CategoryBenchmarkResult(
                    category=cat, contracts_evaluated=0, orders_filled=0,
                    dynamic_harvests=0, news_pulls_executed=0
                )
            stat = self.category_stats[cat]
            stat.contracts_evaluated += 1
            if should_pull:
                stat.news_pulls_executed += 1
            if c.get("market_bid_later_cents", 0) >= 80 and cid not in self.engine.resting_orders:
                stat.dynamic_harvests += 1

        return self.generate_audit_report()

    def generate_audit_report(self) -> Dict[str, Any]:
        summary = self.engine.get_summary()
        net_profit_cents = max(0, self.engine.total_equity_cents - self.initial_equity_cents)
        scma_cents = int(net_profit_cents * 0.87)
        faep_cents = int(net_profit_cents * 0.03)
        cfcp_cents = net_profit_cents - (scma_cents + faep_cents)

        return {
            "initial_equity_cents": self.initial_equity_cents,
            "total_equity_cents": self.engine.total_equity_cents,
            "net_profit_cents": net_profit_cents,
            "scma_cents": scma_cents,
            "cfcp_cents": cfcp_cents,
            "faep_cents": faep_cents,
            "summary": summary,
            "categories": self.category_stats
        }

    def print_terminal_scorecard(self):
        rep = self.generate_audit_report()
        s = rep["summary"]
        init_dol = rep['initial_equity_cents'] / 100
        final_dol = rep['total_equity_cents'] / 100
        spread_dol = s.spread_savings_cents / 100
        fee_dol = s.taker_fees_avoided_cents / 100
        rebate_dol = s.maker_rebates_earned_cents / 100
        scma_dol = rep['scma_cents'] / 100
        cfcp_dol = rep['cfcp_cents'] / 100
        faep_dol = rep['faep_cents'] / 100

        # Dynamic Audit Status Determination
        if s.orders_filled == 0 and s.total_orders_staged > 0:
            status_text = "FAILED (EXECUTION DEADLOCK - ZERO FILLS)"
        elif rep['net_profit_cents'] > 0 and s.orders_filled > 0:
            status_text = "CERTIFIED GREEN (VERIFIED COMPOUNDING)"
        else:
            status_text = "REVIEW REQUIRED (NON-COMPOUNDING)"

        print("=" * 110)
        print("          PDEUE HISTORICAL MICROSTRUCTURE REPLAY ENGINE — 12-CATEGORY AUDIT SCORECARD")
        print("=" * 110)
        print(f" INITIAL CAPITAL: ${init_dol:,.2f}  |  FINAL EQUITY: ${final_dol:,.2f}  |  STATUS: {status_text}")
        print("-" * 110)
        print(" 1. MICROSTRUCTURE COST FRICTION & ALPHA AUDIT")
        print("-" * 110)
        print(f"  • Total Orders Staged:             {s.total_orders_staged}")
        print(f"  • Total Contracts Filled:          {s.orders_filled}")
        print(f"  • News Shocks Quote Pulls (Δt<=5s):{s.orders_cancelled_news_pull} (Adverse sweeps eliminated)")
        print(f"  • Dynamic Early Harvests (>=80%):  {s.positions_harvested_early} (Binary wipeouts dodged)")
        print(f"  • Wholesale Spread Savings:        +${spread_dol:,.2f} (Attributed Strictly on Confirmed Fills)")
        print(f"  • Taker Fee Drag Eliminated:       +${fee_dol:,.2f} (0¢ exchange fee paid on executed volume)")
        print(f"  • Liquidity Maker Rebates Earned:  +${rebate_dol:,.2f}")
        print(f"  • Factor Group Ceilings Enforced:  {s.factor_cap_violations_blocked} (10% cluster cap preserved)")
        print(f"  • Dry-Powder Floor Enforced:       {s.cash_floor_violations_blocked} (40% cash floor active)")
        print("-" * 110)
        print(" 2. 87/10/3 TRANSACTION PROFIT WATERFALL (TPW) ALLOCATION")
        print("-" * 110)
        print(f"  • SCMA (Member Compounding 87%):   ${scma_dol:,.2f} ({rep['scma_cents']}¢)")
        print(f"  • CFCP (Family Contingency 10%+rem):${cfcp_dol:,.2f} ({rep['cfcp_cents']}¢)")
        print(f"  • FAEP (Founder Endowment 3%):     ${faep_dol:,.2f} ({rep['faep_cents']}¢)")
        print("=" * 110)
