"""
Priority Eviction Engine (B7-EXE-EVICT)
Enforces:
1. Max 6 concurrent active orders by default.
2. 40% uncommitted dry powder floor.
3. Strict < 6.0h expiry horizon filtering.
4. Admission at 3% net edge and preemption at a 10 percentage-point uplift.
5. Strict non-eviction of filled or partially-filled inventory.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

class PriorityEvictionManager:
    def __init__(
        self,
        max_concurrent_orders: int = 6,
        dry_powder_floor_pct: float = 0.40,
        max_expiry_hours: Optional[float] = 6.0,
        preemption_alpha_threshold: float = 0.03,
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

    @staticmethod
    def _money(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 9_223_372_036_854_775_807:
            raise ValueError(f"{name} must be a non-negative signed 64-bit integer in cents")
        return value

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
            "stake_cents": self._money(stake_cents, "stake_cents"),
            "status": "RESTING",
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

    def mark_order_filled(self, order_id: str) -> None:
        """Transitions an order to filled inventory. Filled inventory is strictly non-evictable."""
        if order_id in self.resting_orders:
            order = self.resting_orders.pop(order_id)
            order["status"] = "FILLED"
            self.filled_orders[order_id] = order

    def mark_order_partially_filled(self, order_id: str) -> None:
        """Move any partly executed order into immutable inventory."""
        if order_id in self.resting_orders:
            order = self.resting_orders.pop(order_id)
            order["status"] = "PARTIALLY_FILLED"
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
        - Requires at least 3% candidate net edge.
        - Strictly forbids evicting filled and partially-filled positions.
        """
        candidate_edge = candidate.get("net_edge", 0.0)
        candidate_stake = self._money(candidate.get("proposed_stake_cents", 0), "proposed_stake_cents")
        total_equity_cents = self._money(total_equity_cents, "total_equity_cents")
        currently_committed_cents = self._money(currently_committed_cents, "currently_committed_cents")
        expiry_hours = candidate.get("expiry_hours", 1.0)

        if candidate_edge < self.preemption_alpha_threshold:
            return {
                "admitted": False,
                "reason": "EDGE_BELOW_ADMISSION_THRESHOLD",
                "eviction_target": None,
            }

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

        # 3. Check for evictable resting bids (executed inventory is immune)
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
