"""RC-C deterministic replay and network-isolated continuous paper soak."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from collections import deque
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from app.adapters.rate_limiter import VenueRateLimiter
from app.domain.capital_ledger import CapitalLedger
from app.domain.dynamic_spread_kelly import DynamicSpreadKellyRegime
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.telemetry_sink import TelemetryHealthSink, require_cents


class PaperSoakRunner:
    """Bounded-state simulator; it contains no live venue or network clients."""

    ACCELERATED_PIT = "accelerated-pit"
    CONTINUOUS_PAPER = "continuous-paper"
    DOMAINS = ("WEATHER", "MACRO", "SPORTS", "CRYPTO")

    def __init__(
        self,
        total_cycles: int = 51_840,
        cycle_interval_sec: float = 5.0,
        health_export_interval: int = 4_320,
        health_export_path: str = "health_summary.json",
        initial_balance_cents: int = 10_000,
        limiter: Optional[VenueRateLimiter] = None,
        mode: str = CONTINUOUS_PAPER,
        max_concurrent_orders: int = 12,
        dry_powder_floor: float = 0.40,
    ):
        if mode not in (self.ACCELERATED_PIT, self.CONTINUOUS_PAPER):
            raise ValueError("unsupported soak mode")
        if total_cycles < 0 or cycle_interval_sec < 0 or health_export_interval <= 0:
            raise ValueError("cycle limits and intervals must be non-negative")
        self.initial_balance_cents = require_cents(initial_balance_cents, "initial_balance_cents")
        if self.initial_balance_cents < 0:
            raise ValueError("initial balance cannot be negative")
        if max_concurrent_orders <= 0:
            raise ValueError("max_concurrent_orders must be positive")
        if not 0 <= dry_powder_floor < 1:
            raise ValueError("dry_powder_floor must be in [0, 1)")
        self.mode, self.total_cycles = mode, total_cycles
        self.cycle_interval_sec, self.health_export_interval = cycle_interval_sec, health_export_interval
        self.current_cycle, self.is_running = 0, False
        self.partition = "PARTITION_2_ENHANCED_ALPHA"
        self.limiter = limiter or VenueRateLimiter()
        self.sink = TelemetryHealthSink(health_export_path)
        self.ledger = CapitalLedger(initial_balance_cents=self.initial_balance_cents)
        self.eviction_manager = PriorityEvictionManager(
            max_concurrent_orders=max_concurrent_orders,
            dry_powder_floor_pct=dry_powder_floor,
            min_edge_delta=0.10,
        )
        self.kelly_regime = DynamicSpreadKellyRegime()
        self.ledger.register_member_account("founder_scma", seed_capital_cents=self.initial_balance_cents)
        self.maker_stats = {"posted": 0, "filled": 0, "expired": 0}
        self.phase_bc_metrics = {"scratched_legs": 0, "sniped_quotes": 0, "rebalances_triggered": 0}
        self.spread_distributions = {"WEATHER": .02, "MACRO": .03, "SPORTS": .015, "CRYPTO": .025}
        self.circuit_breaker = {"is_tripped": False, "trip_reason": None}
        # Six-hour samples only: 72 hours needs at most 13 integers.
        self.equity_trajectory_cents: deque[int] = deque(maxlen=13)
        self.equity_trajectory_cents.append(self.initial_balance_cents)
        self._last_snapshot_time = -1

    @property
    def equity_cents(self) -> int:
        return require_cents(
            self.ledger.members["founder_scma"]["balance_cents"]
            + self.ledger.central_family_pool_cents + self.ledger.founder_pool_cents,
            "equity_cents",
        )

    def _assert_dry_powder(self, committed_cents: int) -> None:
        committed_cents = require_cents(committed_cents, "committed_cents")
        # Integer comparison avoids rounding: uncommitted/equity >= 40/100.
        if committed_cents < 0 or (self.equity_cents - committed_cents) * 100 < self.equity_cents * 40:
            self.circuit_breaker.update(is_tripped=True, trip_reason="DRY_POWDER_FLOOR_BREACH")
            raise ValueError("order would breach the 40% dry-powder floor")

    def _committed_cents(self) -> int:
        """Return capital attached to orders and non-evictable filled inventory."""
        orders = (*self.eviction_manager.resting_orders.values(),
                  *self.eviction_manager.filled_orders.values())
        return sum(require_cents(order["stake_cents"], "stake_cents") for order in orders)

    def execute_cycle(self, snapshot: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self.current_cycle += 1
        if snapshot is not None:
            available_at = int(snapshot["available_at"])
            observed_at = int(snapshot["observed_at"])
            if available_at < observed_at or available_at < self._last_snapshot_time:
                raise ValueError("PIT snapshots must be availability-ordered without lookahead")
            domain = str(snapshot["domain"]).upper()
            if domain not in self.DOMAINS:
                raise ValueError("unknown contract domain")
            self._last_snapshot_time = available_at
        posted = filled = expired = evicted = 0
        admitted = False
        allocation_cents = 0
        if not self.circuit_breaker["is_tripped"] and self.limiter.can_proceed("KALSHI") and self.limiter.can_proceed("POLYMARKET"):
            market = snapshot or {}
            domain = str(market.get("domain", self.DOMAINS[(self.current_cycle - 1) % len(self.DOMAINS)])).upper()
            spread = float(market.get("spread", self.spread_distributions[domain]))
            active_fraction = self.kelly_regime.calculate_active_fraction(spread)
            requested_cents = require_cents(
                market.get("order_cents", self.equity_cents * 5 // 100), "order_cents"
            )
            # The requested order is a full (25%) regime quote. Wider spreads
            # scale it down, while never allowing sizing to increase it.
            allocation_cents = min(
                requested_cents,
                int(requested_cents * active_fraction / self.kelly_regime.base_fraction),
            )
            committed_cents = self._committed_cents()
            order_id = str(market.get("order_id", market.get("contract_id", f"SOAK-{self.current_cycle:08d}")))
            candidate = {
                "net_edge": float(market.get("net_edge", 0.05)),
                "proposed_stake_cents": allocation_cents,
                "expiry_hours": float(market.get("expiry_hours", 1.0)),
            }
            decision = self.eviction_manager.evaluate_preemption(
                candidate, self.equity_cents, committed_cents
            )
            target = decision["eviction_target"]
            replaced_stake = target["stake_cents"] if target is not None else 0
            max_committed = int(
                self.equity_cents * (1.0 - self.eviction_manager.dry_powder_floor_pct)
            )
            preserves_dry_powder = (
                committed_cents - replaced_stake + allocation_cents <= max_committed
            )
            if decision["admitted"] and preserves_dry_powder:
                if target is not None:
                    self.eviction_manager.execute_eviction(target["order_id"])
                    evicted = expired = 1
                self.eviction_manager.register_resting_order(
                    order_id, str(market.get("ticker", order_id)), domain,
                    candidate["net_edge"], allocation_cents,
                )
                admitted = True
                posted = 1
                outcome = str(market.get("execution_status", "FILLED" if snapshot is None else "RESTING")).upper()
                if outcome == "FILLED":
                    self.eviction_manager.mark_order_filled(order_id)
                    filled = 1
                    # Paper fills settle immediately; recording the transition
                    # through the manager preserves fill immunity while closed
                    # inventory no longer consumes an active-order slot.
                    if bool(market.get("settle_on_fill", True)):
                        self.eviction_manager.filled_orders.pop(order_id)
                elif outcome == "EXPIRED":
                    self.eviction_manager.resting_orders.pop(order_id)
                    expired = 1
                elif outcome != "RESTING":
                    raise ValueError("execution_status must be RESTING, FILLED, or EXPIRED")
            self.maker_stats["posted"] += posted
            self.maker_stats["filled"] += filled
            self.maker_stats["expired"] += expired
            if self.current_cycle % 25 == 0:
                self.phase_bc_metrics["sniped_quotes"] += 1
        if self.current_cycle % self.health_export_interval == 0:
            self.equity_trajectory_cents.append(self.equity_cents)
            self.flush()
        fill_rate = self.maker_stats["filled"] / self.maker_stats["posted"] if self.maker_stats["posted"] else 0.0
        return {"cycle": self.current_cycle, "posted": posted, "filled": filled,
                "expired": expired, "admitted": admitted, "allocation_cents": allocation_cents,
                "resting_bids": len(self.eviction_manager.resting_orders),
                "slot_occupancy": len(self.eviction_manager.resting_orders) + len(self.eviction_manager.filled_orders),
                "fill_rate": fill_rate, "evictions": evicted,
                "total_evictions": len(self.eviction_manager.eviction_history),
                "domain": snapshot.get("domain") if snapshot else None,
                "phase_bc_metrics": dict(self.phase_bc_metrics),
                "rate_limiter_warnings": self.limiter.warnings_count}

    def replay(self, snapshots: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Replay only data known at each snapshot's availability time."""
        if self.mode != self.ACCELERATED_PIT:
            raise RuntimeError("replay is available only in accelerated-pit mode")
        records = [dict(item) for item in snapshots]
        records.sort(key=lambda item: (int(item["available_at"]), str(item.get("contract_id", ""))))
        self.total_cycles = len(records)
        return [self.execute_cycle(item) for item in records]

    def flush(self) -> str:
        if not self.equity_trajectory_cents or self.equity_trajectory_cents[-1] != self.equity_cents:
            self.equity_trajectory_cents.append(self.equity_cents)
        payload = self.sink.compile_health_payload(
            {"founder_scma": self.ledger.members["founder_scma"]["balance_cents"],
             "cfcp": self.ledger.central_family_pool_cents, "faep": self.ledger.founder_pool_cents},
            self.maker_stats, self.spread_distributions, self.circuit_breaker,
            self.limiter.warnings_count, cycle=self.current_cycle,
            equity_trajectory_cents=list(self.equity_trajectory_cents),
            latency_sniping_events=self.phase_bc_metrics["sniped_quotes"],
            legging_scratches=self.phase_bc_metrics["scratched_legs"], collateral_drift_cents=0,
        )
        payload["partition_tag"], payload["mode"] = self.partition, self.mode
        return self.sink.export_health_summary(payload)

    async def run(self) -> None:
        self.is_running = True
        try:
            while self.is_running and self.current_cycle < self.total_cycles:
                self.execute_cycle()
                if self.is_running and self.current_cycle < self.total_cycles:
                    await asyncio.sleep(self.cycle_interval_sec)
        finally:
            self.is_running = False
            self.flush()

    def stop(self, *_: object) -> None:
        """Signal-safe request; the run finally block performs the durable flush."""
        self.is_running = False

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(PaperSoakRunner.ACCELERATED_PIT, PaperSoakRunner.CONTINUOUS_PAPER), default=PaperSoakRunner.CONTINUOUS_PAPER)
    parser.add_argument("--output", default="/var/lib/pdeue-paper-soak/health_summary.json")
    parser.add_argument("--max-concurrent-orders", type=int, default=12)
    parser.add_argument("--dry-powder-floor", type=float, default=0.40)
    args = parser.parse_args()
    runner = PaperSoakRunner(
        mode=args.mode, health_export_path=args.output,
        max_concurrent_orders=args.max_concurrent_orders,
        dry_powder_floor=args.dry_powder_floor,
    )
    runner.install_signal_handlers()
    asyncio.run(runner.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
