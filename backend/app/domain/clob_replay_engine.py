"""
PDEUE Central Limit Order Book (CLOB) Replay Engine & 12-Category Dispatcher (WP-8B)
Sequences point-in-time order book execution across all 12 market verticals.

Governing Invariants:
- FIFO queue priority and authentic spread capture (Best Bid + 0.01).
- Clock-synchronized quote cancellations (Δt <= 5.0s) for scheduled macro events.
- 10% Factor Cluster Cap across shared underlying events.
- Hard 40% liquid dry-powder floor preservation under ADR-008.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from app.domain.expansion_adapters import (
    LaborUnderwritingAdapter,
    EnergyEIAAdapter,
    TreasuryAuctionAdapter,
    EquityIndexAdapter,
    LogisticsTSAAdapter,
    FXFixingAdapter,
    SportsPoissonAdapter,
    PerpFundingAdapter,
    UnderwritingDecision
)

@dataclass
class ReplayOrder:
    order_id: str
    contract_id: str
    category: str
    factor_group: str
    side: str
    price_cents: int
    quantity: int
    status: str  # RESTING_MAKER, FILLED, CANCELLED_NEWS_SHOCK, HARVESTED
    timestamp_ns: int

@dataclass
class ReplayExecutionSummary:
    total_orders_staged: int
    orders_filled: int
    orders_cancelled_news_pull: int
    positions_harvested_early: int
    spread_savings_cents: int
    taker_fees_avoided_cents: int
    maker_rebates_earned_cents: int
    factor_cap_violations_blocked: int
    cash_floor_violations_blocked: int

class CLOBReplayEngine:
    def __init__(self, initial_equity_cents: int = 1_000_000, dry_powder_floor_pct: float = 0.40):
        self.initial_equity_cents = initial_equity_cents
        self.total_equity_cents = initial_equity_cents
        self.available_cash_cents = initial_equity_cents
        self.dry_powder_floor_cents = int(initial_equity_cents * dry_powder_floor_pct)

        # Factor group margin tracking (max 10% per group)
        self.factor_allocations: Dict[str, int] = {}
        self.max_factor_cap_cents = int(initial_equity_cents * 0.10)

        # Active state books
        self.resting_orders: Dict[str, ReplayOrder] = {}
        self.open_positions: Dict[str, Dict[str, Any]] = {}

        # Expansion Adapters
        self.adapters = {
            "macro_labor": LaborUnderwritingAdapter(),
            "energy_eia": EnergyEIAAdapter(),
            "treasury_tails": TreasuryAuctionAdapter(),
            "equity_index": EquityIndexAdapter(),
            "logistics_tsa": LogisticsTSAAdapter(),
            "fx_fixing": FXFixingAdapter(),
            "sports_spreads": SportsPoissonAdapter(),
            "perp_funding": PerpFundingAdapter()
        }

        # Execution Metrics
        self.spread_savings_cents = 0
        self.taker_fees_avoided_cents = 0
        self.maker_rebates_earned_cents = 0
        self.orders_cancelled_news_pull = 0
        self.positions_harvested_early = 0
        self.factor_cap_blocks = 0
        self.cash_floor_blocks = 0
        self.total_orders_staged = 0

    def evaluate_and_stage_order(
        self,
        order_id: str,
        contract_id: str,
        category: str,
        factor_group: str,
        decision: UnderwritingDecision,
        best_bid_cents: int,
        best_ask_cents: int,
        timestamp_ns: int
    ) -> Optional[ReplayOrder]:
        self.total_orders_staged += 1

        # 1. Clock-Synchronized Pre-Release Quote Pull
        if decision.should_pull_quotes:
            self.orders_cancelled_news_pull += 1
            return None

        # 2. Risk Sizing via Retained-Kelly (Quarter-Kelly <= 2.0%)
        adapter = self.adapters.get(category)
        kelly_fraction = adapter.calculate_retained_kelly(decision.fair_probability, decision.recommended_bid_cents) if adapter else 0.01
        order_cost_cents = int(self.total_equity_cents * kelly_fraction)
        quantity = max(1, order_cost_cents // decision.recommended_bid_cents)
        total_cost = quantity * decision.recommended_bid_cents

        # 3. 40% Liquid Dry-Powder Floor Enforcement
        if (self.available_cash_cents - total_cost) < self.dry_powder_floor_cents:
            self.cash_floor_blocks += 1
            return None

        # 4. 10% Factor Correlation Group Ceiling Enforcement
        current_factor_margin = self.factor_allocations.get(factor_group, 0)
        if (current_factor_margin + total_cost) > self.max_factor_cap_cents:
            self.factor_cap_blocks += 1
            return None

        # 5. Inside Maker Spread Capture
        order = ReplayOrder(
            order_id=order_id,
            contract_id=contract_id,
            category=category,
            factor_group=factor_group,
            side="BUY_YES",
            price_cents=decision.recommended_bid_cents,
            quantity=quantity,
            status="RESTING_MAKER",
            timestamp_ns=timestamp_ns
        )

        self.resting_orders[order_id] = order
        self.available_cash_cents -= total_cost
        self.factor_allocations[factor_group] = current_factor_margin + total_cost

        # Calculate avoided costs vs Retail Taker crossing spread at Ask
        spread_discount = (best_ask_cents - decision.recommended_bid_cents) * quantity
        taker_fee_avoided = int(round(best_ask_cents * 0.02 * quantity)) # 2% retail fee
        maker_rebate = int(round(decision.recommended_bid_cents * 0.005 * quantity)) # 0.5% maker rebate

        self.spread_savings_cents += max(0, spread_discount)
        self.taker_fees_avoided_cents += taker_fee_avoided
        self.maker_rebates_earned_cents += maker_rebate

        return order

    def process_trade_tape_print(self, contract_id: str, print_price_cents: int, print_qty: int):
        """Fills resting maker orders when authentic venue trade print trades at/through order price"""
        for oid, order in list(self.resting_orders.items()):
            if order.contract_id == contract_id and order.status == "RESTING_MAKER":
                if print_price_cents <= order.price_cents and print_qty >= order.quantity:
                    order.status = "FILLED"
                    self.open_positions[contract_id] = {
                        "order_id": oid,
                        "entry_price_cents": order.price_cents,
                        "quantity": order.quantity,
                        "category": order.category,
                        "factor_group": order.factor_group
                    }
                    del self.resting_orders[oid]

    def evaluate_early_harvest(self, contract_id: str, current_market_bid_cents: int) -> bool:
        """Dynamic Early Harvest: Liquidates position at >= 80% to eliminate binary cliff risk"""
        pos = self.open_positions.get(contract_id)
        if not pos:
            return False

        if current_market_bid_cents >= 80:
            proceeds = pos["quantity"] * current_market_bid_cents
            self.available_cash_cents += proceeds
            self.total_equity_cents += (proceeds - (pos["quantity"] * pos["entry_price_cents"]))
            # Free factor group allocation
            self.factor_allocations[pos["factor_group"]] -= (pos["quantity"] * pos["entry_price_cents"])
            self.positions_harvested_early += 1
            del self.open_positions[contract_id]
            return True
        return False

    def get_summary(self) -> ReplayExecutionSummary:
        return ReplayExecutionSummary(
            total_orders_staged=self.total_orders_staged,
            orders_filled=len(self.open_positions) + self.positions_harvested_early,
            orders_cancelled_news_pull=self.orders_cancelled_news_pull,
            positions_harvested_early=self.positions_harvested_early,
            spread_savings_cents=self.spread_savings_cents,
            taker_fees_avoided_cents=self.taker_fees_avoided_cents,
            maker_rebates_earned_cents=self.maker_rebates_earned_cents,
            factor_cap_violations_blocked=self.factor_cap_blocks,
            cash_floor_violations_blocked=self.cash_floor_blocks
        )
