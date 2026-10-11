"""
PDEUE Central Limit Order Book (CLOB) Replay Engine & 12-Category Dispatcher
Sequences point-in-time order book execution across all 12 market verticals.

Governing Invariants:
- Partial Fills: Cumulative fills tracked per order.
- Post-Fill Attribution: Spread savings and fee avoidance credited ONLY on executed volume.
- Order TTL: Unfilled orders expire cleanly and release margin back to cash.
- Hard 40% liquid dry-powder floor and 10% factor caps preserved under ADR-008.
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
    best_ask_cents: int
    filled_quantity: int = 0
    status: str = "RESTING_MAKER"  # RESTING_MAKER, FILLED, EXPIRED_UNFILLED, CANCELLED_NEWS_SHOCK
    timestamp_ns: int = 0

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

        # 12 Category Adapters
        self.adapters = {
            "macro_labor": LaborUnderwritingAdapter(),
            "energy_eia": EnergyEIAAdapter(),
            "treasury_tails": TreasuryAuctionAdapter(),
            "equity_index": EquityIndexAdapter(),
            "logistics_tsa": LogisticsTSAAdapter(),
            "fx_fixing": FXFixingAdapter(),
            "sports_spreads": SportsPoissonAdapter(),
            "perp_funding": PerpFundingAdapter(),
            # Fallback bindings for core verticals
            "weather_noaa": LogisticsTSAAdapter(),
            "fed_rates": TreasuryAuctionAdapter(),
            "macro_cpi": LaborUnderwritingAdapter(),
            "crypto_brackets": EquityIndexAdapter()
        }

        # Execution Metrics (Credited strictly upon fill)
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
        kelly_fraction = adapter.calculate_retained_kelly(decision.fair_probability, decision.recommended_bid_cents) if adapter else 0.015
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

        # 5. Place Resting Maker Order
        order = ReplayOrder(
            order_id=order_id,
            contract_id=contract_id,
            category=category,
            factor_group=factor_group,
            side="BUY_YES",
            price_cents=decision.recommended_bid_cents,
            quantity=quantity,
            best_ask_cents=best_ask_cents,
            status="RESTING_MAKER",
            timestamp_ns=timestamp_ns
        )

        self.resting_orders[order_id] = order
        self.available_cash_cents -= total_cost
        self.factor_allocations[factor_group] = current_factor_margin + total_cost
        return order

    def process_trade_tape_print(self, contract_id: str, print_price_cents: int, filled_qty: int):
        """Fills resting maker orders incrementally upon authentic tape print"""
        for oid, order in list(self.resting_orders.items()):
            if order.contract_id == contract_id and order.status == "RESTING_MAKER":
                if print_price_cents <= order.price_cents and filled_qty > 0:
                    order.filled_quantity += filled_qty
                    
                    # Credit savings ONLY on confirmed executed shares
                    spread_saved = (order.best_ask_cents - order.price_cents) * filled_qty
                    taker_avoided = int(round(order.best_ask_cents * 0.02 * filled_qty))
                    maker_rebate = int(round(order.price_cents * 0.005 * filled_qty))

                    self.spread_savings_cents += max(0, spread_saved)
                    self.taker_fees_avoided_cents += taker_avoided
                    self.maker_rebates_earned_cents += maker_rebate

                    if order.filled_quantity >= order.quantity:
                        order.status = "FILLED"
                        self.open_positions[contract_id] = {
                            "order_id": oid,
                            "entry_price_cents": order.price_cents,
                            "quantity": order.filled_quantity,
                            "category": order.category,
                            "factor_group": order.factor_group
                        }
                        del self.resting_orders[oid]

    def expire_unfilled_order(self, order_id: str):
        """Releases locked capital if an order times out or expires without full fills"""
        order = self.resting_orders.get(order_id)
        if order:
            unfilled_qty = order.quantity - order.filled_quantity
            unfilled_cents = unfilled_qty * order.price_cents
            self.available_cash_cents += unfilled_cents
            self.factor_allocations[order.factor_group] -= unfilled_cents

            if order.filled_quantity > 0:
                self.open_positions[order.contract_id] = {
                    "order_id": order_id,
                    "entry_price_cents": order.price_cents,
                    "quantity": order.filled_quantity,
                    "category": order.category,
                    "factor_group": order.factor_group
                }
            del self.resting_orders[order_id]

    def evaluate_early_harvest(self, contract_id: str, current_market_bid_cents: int) -> bool:
        """Dynamic Early Harvest: Liquidates position at >= 80% to eliminate binary cliff risk"""
        pos = self.open_positions.get(contract_id)
        if not pos:
            return False

        if current_market_bid_cents >= 80:
            proceeds = pos["quantity"] * current_market_bid_cents
            cost_basis = pos["quantity"] * pos["entry_price_cents"]
            self.available_cash_cents += proceeds
            self.total_equity_cents += (proceeds - cost_basis)
            self.factor_allocations[pos["factor_group"]] -= cost_basis
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
