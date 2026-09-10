"""
Priority Eviction Engine (B7-EXE-EVICT)
Enforces:
1. Max 5 concurrent active orders.
2. 40% uncommitted dry powder floor.
3. Strict < 6.0h expiry horizon filtering.
4. Preemption of unfilled resting limit bids when candidate alpha >= 20.0%.
5. Strict non-eviction of filled inventory (prevents taker spread penalties).
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

class PriorityEvictionManager:
    def __init__(
        self,
        max_concurrent_orders: int = 5,
        dry_powder_floor_pct: float = 0.40,
        max_expiry_hours: Optional[float] = 6.0,
        preemption_alpha_threshold: float = 0.20,
        min_edge_delta: float = 0.10,
    ):
        self.max_concurrent_orders = max_concurrent_orders
        self.dry_powder_floor_pct = dry_powder_floor_pct
        self.max_expiry_hours = max_expiry_hours
        self.preemption_alpha_threshold = preemption_alpha_threshold
        self.min_edge_delta = min_edge_delta
        self.resting_orders: Dict[str, Dict[str, Any]] = {}
        self.filled_orders: Dict[str, Dict[str, Any]] = {}
        self.eviction_history: List[Dict[str, Any]] = []

    def register_resting_order(
        self,
        order_id: str,
        ticker: str,
        domain: str,
        net_edge: float,
        stake_cents: int,
    ) -> None:
        """Registers an unfilled resting limit bid currently sitting in an exchange order book."""
        self.resting_orders[order_id] = {
            "order_id": order_id,
            "ticker": ticker,
            "domain": domain,
            "net_edge": net_edge,
            "stake_cents": stake_cents,
            "status": "RESTING",
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

    def mark_order_filled(self, order_id: str) -> None:
        """Transitions an order to filled inventory. Filled inventory is strictly non-evictable."""
        if order_id in self.resting_orders:
            order = self.resting_orders.pop(order_id)
            order["status"] = "FILLED"
            self.filled_orders[order_id] = order

    def evaluate_preemption(
        self,
        candidate: Dict[str, Any],
        total_equity_cents: int,
        currently_committed_cents: int,
    ) -> Dict[str, Any]:
        """
        Evaluates preemption eligibility.
        - Rejects candidates with expiry horizon > max_expiry_hours.
        - Passes normal admission if capacity and 40% dry powder floor allow.
        - Evaluates resting order preemption if candidate net edge >= 20.0%.
        - Strictly forbids evicting filled positions.
        """
        candidate_edge = candidate.get("net_edge", 0.0)
        candidate_stake = candidate.get("proposed_stake_cents", 0)
        expiry_hours = candidate.get("expiry_hours", 1.0)

        # 1. Hard expiry horizon filter (< 6h when configured)
        if self.max_expiry_hours is not None and expiry_hours > self.max_expiry_hours:
            return {
                "admitted": False,
                "reason": "EXPIRY_EXCEEDS_HORIZON_CEILING",
                "eviction_target": None,
            }

        max_allocatable_cents = int(total_equity_cents * (1.0 - self.dry_powder_floor_pct))
        available_budget_cents = max_allocatable_cents - currently_committed_cents
        total_active_orders = len(self.resting_orders) + len(self.filled_orders)

        # 2. Normal admission check
        if available_budget_cents >= candidate_stake and total_active_orders < self.max_concurrent_orders:
            return {
                "admitted": True,
                "reason": "NORMAL_ADMISSION",
                "eviction_target": None,
            }

        # 3. Preemption alpha threshold check (must be >= 20.0% edge)
        if candidate_edge < self.preemption_alpha_threshold:
            return {
                "admitted": False,
                "reason": "ALPHA_BELOW_PREEMPTION_THRESHOLD",
                "eviction_target": None,
            }

        # 4. Check for evictable resting bids (filled orders are immune)
        if not self.resting_orders:
            return {
                "admitted": False,
                "reason": "NO_UNFILLED_RESTING_ORDERS_AVAILABLE",
                "eviction_target": None,
            }

        # 5. Identify lowest-edge resting order
        lowest_resting = min(self.resting_orders.values(), key=lambda x: x["net_edge"])
        edge_delta = candidate_edge - lowest_resting["net_edge"]

        if edge_delta < self.min_edge_delta:
            return {
                "admitted": False,
                "reason": f"INSUFFICIENT_DELTA_{edge_delta:.3f}_MIN_{self.min_edge_delta:.3f}",
                "eviction_target": None,
            }

        return {
            "admitted": True,
            "reason": "PREEMPTION_APPROVED",
            "eviction_target": lowest_resting,
            "edge_delta": edge_delta,
        }

    def execute_eviction(self, order_id: str, reason: str = "ALPHA_PREEMPTION") -> Dict[str, Any]:
        """Evicts an unfilled resting order, cancelling venue limit bid with zero spread penalty."""
        if order_id not in self.resting_orders:
            raise ValueError(f"Order {order_id} cannot be evicted: not resting or already filled.")

        evicted = self.resting_orders.pop(order_id)
        evicted["status"] = "CANCELLED_EVICTED"
        evicted["eviction_reason"] = reason
        evicted["evicted_at"] = datetime.now(timezone.utc).isoformat()
        self.eviction_history.append(evicted)
        return evicted
