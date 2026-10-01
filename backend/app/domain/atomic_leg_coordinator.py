"""Offline coordinator for bounded-risk, multi-leg executions."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Sequence


class AtomicLegCoordinator:
    def __init__(self, leg_timeout_ms: int = 750, clock: Callable[[], float] = time.monotonic):
        if leg_timeout_ms <= 0:
            raise ValueError("leg_timeout_ms must be positive")
        self.leg_timeout_ms = int(leg_timeout_ms)
        self.leg_timeout_sec = self.leg_timeout_ms / 1000
        self._clock = clock
        self.scratched_positions: List[Dict[str, Any]] = []

    @staticmethod
    def route_order(legs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(legs) < 2:
            raise ValueError("at least two legs are required")
        # Least liquid first: lower depth dominates, wider spread breaks ties.
        return sorted(legs, key=lambda leg: (int(leg.get("depth_cents", 0)), -float(leg.get("spread", 0))))

    def coordinate_legs(
        self, primary_leg: Dict[str, Any], secondary_leg: Dict[str, Any],
        simulate_leg2_latency_sec: float = 0.0, simulate_leg2_fail: bool = False,
        max_loss_budget_cents: int = 0,
    ) -> Dict[str, Any]:
        if isinstance(max_loss_budget_cents, bool) or not isinstance(max_loss_budget_cents, int) or max_loss_budget_cents < 0:
            raise ValueError("max_loss_budget_cents must be a non-negative integer")
        leg1, leg2 = self.route_order((primary_leg, secondary_leg))
        primary_fill = {**leg1, "order_type": "RESTING_LIMIT", "status": "FILLED", "fill_time": self._clock()}
        timed_out = simulate_leg2_latency_sec * 1000 > self.leg_timeout_ms
        if timed_out or simulate_leg2_fail:
            requested_loss = int(leg1.get("scratch_loss_cents", max_loss_budget_cents))
            bounded_loss = min(max_loss_budget_cents, max(0, requested_loss))
            scratch_event = {
                "action": "IOC_MARKETABLE_LIMIT_SCRATCH",
                "order_type": "IOC_MARKETABLE_LIMIT",
                "primary_leg_id": leg1.get("leg_id", "LEG-1"),
                "secondary_leg_id": leg2.get("leg_id", "LEG-2"),
                "reason": "LEG_2_TIMEOUT_EXCEEDED" if timed_out else "LEG_2_FILL_REJECTED",
                "max_loss_budget_cents": max_loss_budget_cents,
                "realized_loss_cents": bounded_loss,
                "status": "SCRATCHED",
            }
            self.scratched_positions.append(scratch_event)
            return {"is_atomic_success": False, "outcome": "SCRATCHED", "primary_fill": primary_fill, "secondary_fill": None, "scratch_event": scratch_event}
        secondary_fill = {**leg2, "order_type": "MARKETABLE_LIMIT", "status": "FILLED", "fill_time": self._clock()}
        return {"is_atomic_success": True, "outcome": "COMPLETE_SET_FILLED", "primary_fill": primary_fill, "secondary_fill": secondary_fill, "scratch_event": None}
