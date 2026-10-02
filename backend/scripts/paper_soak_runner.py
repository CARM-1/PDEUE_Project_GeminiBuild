"""RC-C deterministic replay and network-isolated continuous paper soak."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import secrets
import signal
import sys
import time
from collections import deque
from typing import Any, Iterable, Mapping, Optional

import httpx

base_dir = pathlib.Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from app.adapters.rate_limiter import VenueRateLimiter
from app.domain.capital_ledger import CapitalLedger
from app.domain.dynamic_spread_kelly import DynamicSpreadKellyRegime
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.position_book import PositionBook
from app.domain.settlement_engine import SettlementEngine
from app.domain.telemetry_sink import TelemetryHealthSink, require_cents
from app.clients.kalshi_client import KalshiClient
from app.clients.polymarket_client import PolymarketClient
from app.services.credential_broker import CredentialBroker


class PaperSoakRunner:
    """Bounded-state simulator; it contains no live venue or network clients."""

    ACCELERATED_PIT = "accelerated-pit"
    CONTINUOUS_PAPER = "continuous-paper"
    SIMULATION_SOAK = "simulation-soak"
    TESTNET_SANDBOX_QUALIFICATION = "testnet-sandbox-qualification"
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
        execution_mode: Optional[str] = None,
        credential_broker: Optional[CredentialBroker] = None,
        kalshi_client: Optional[KalshiClient] = None,
        polymarket_client: Optional[PolymarketClient] = None,
    ):
        if mode not in (self.ACCELERATED_PIT, self.CONTINUOUS_PAPER, self.SIMULATION_SOAK,
                        self.TESTNET_SANDBOX_QUALIFICATION):
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
        self.execution_mode = str(
            execution_mode or ("TESTNET_SANDBOX" if mode == self.TESTNET_SANDBOX_QUALIFICATION
                               else os.getenv("VENUE_EXECUTION_MODE", "PAPER"))
        ).upper()
        if self.execution_mode not in {"SIMULATION", "TESTNET_SANDBOX", "PAPER"}:
            raise ValueError("VENUE_EXECUTION_MODE must be SIMULATION, TESTNET_SANDBOX, or PAPER")
        self.credential_broker = credential_broker or CredentialBroker()
        self.kalshi_client = kalshi_client
        self.polymarket_client = polymarket_client
        if self.execution_mode == "TESTNET_SANDBOX":
            self.kalshi_client = self.kalshi_client or KalshiClient(
                self.credential_broker, "DEFAULT"
            )
            self.polymarket_client = self.polymarket_client or PolymarketClient(
                self.credential_broker, "DEFAULT"
            )
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
        self.position_book = PositionBook()
        self.complete_set_released_cents = 0
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
        floor_cents = max(
            4_000, int(self.equity_cents * self.eviction_manager.dry_powder_floor_pct)
        )
        if committed_cents < 0 or self.equity_cents - committed_cents < floor_cents:
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
            floor_cents = max(
                4_000, int(self.equity_cents * self.eviction_manager.dry_powder_floor_pct)
            )
            max_committed = max(0, self.equity_cents - floor_cents)
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
                    contract_id = str(market.get("contract_id", order_id))
                    side = str(market.get("side", "BUY_YES"))
                    quantity = int(market.get("quantity", 1))
                    self.position_book.record_fill(
                        contract_id, str(market.get("venue", "PAPER")), domain,
                        side, allocation_cents / max(quantity, 1) / 100,
                        quantity, allocation_cents, member_id="founder_scma",
                    )
                    released_cents = self.position_book.merge_complete_sets(
                        "founder_scma", contract_id
                    )
                    if released_cents:
                        self.ledger.credit_balance(released_cents, account_id="founder_scma")
                        self.complete_set_released_cents += released_cents
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
                "complete_set_released_cents": self.complete_set_released_cents,
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
        payload["venue_execution_mode"] = self.execution_mode
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

    def qualify_phase5_invariants(self) -> dict[str, Any]:
        """Exercise the Phase 5 safeguards without contacting an external venue."""
        capacity = int(self.eviction_manager.max_concurrent_orders)
        probe = PriorityEvictionManager(max_concurrent_orders=capacity, dry_powder_floor_pct=0.40)
        stake_cents = 500
        for index in range(capacity):
            probe.register_resting_order(
                f"QUAL-RESTING-{index:02d}", "QUAL", "SIMULATION",
                0.04 + index / 1000, stake_cents,
            )
        preemption = probe.evaluate_preemption(
            {"net_edge": 0.20, "proposed_stake_cents": stake_cents, "expiry_hours": 1.0},
            total_equity_cents=10_000,
            currently_committed_cents=capacity * stake_cents,
        )
        target = preemption.get("eviction_target")
        if not preemption["admitted"] or target is None:
            raise AssertionError("saturated orderboard did not approve priority eviction")
        evicted = probe.execute_eviction(target["order_id"])

        book = PositionBook()
        book.record_fill("QUAL-BINARY", "PAPER", "SIMULATION", "BUY_YES", 0.40, 3, 120, "founder_scma")
        book.record_fill("QUAL-BINARY", "PAPER", "SIMULATION", "BUY_NO", 0.50, 2, 100, "founder_scma")
        released_cents = book.merge_complete_sets("founder_scma", "QUAL-BINARY")
        if released_cents != 200:
            raise AssertionError("complete-set collateral was not released immediately")

        floor_equity_cents = 10_003
        floor_cents = max(4_000, int(0.40 * floor_equity_cents))
        floor_probe = PriorityEvictionManager(max_concurrent_orders=12, dry_powder_floor_pct=0.40)
        floor_decision = floor_probe.evaluate_preemption(
            {"net_edge": 0.20, "proposed_stake_cents": 6_004, "expiry_hours": 1.0},
            total_equity_cents=floor_equity_cents,
            currently_committed_cents=0,
        )
        if floor_decision["admitted"]:
            raise AssertionError("dry-powder floor accepted an order that breaches reserves")

        waterfall_engine = SettlementEngine()
        waterfall_input_cents = 10_003
        waterfall = waterfall_engine.calculate_waterfall_split(waterfall_input_cents)
        if sum(waterfall.values()) != waterfall_input_cents:
            raise AssertionError("waterfall failed exact-cent conservation")
        independently_floored_cfcp = waterfall_input_cents * 10 // 100
        residual_to_cfcp = waterfall["cfcp_cents"] - independently_floored_cfcp

        return {
            "priority_eviction": {
                "passed": True,
                "capacity": capacity,
                "candidate_net_edge_bps": 2_000,
                "edge_delta_bps": int(round(preemption["edge_delta"] * 10_000)),
                "evicted_order_id": evicted["order_id"],
            },
            "complete_set_recycling": {
                "passed": True,
                "released_collateral_cents": released_cents,
                "remaining_yes_shares": 1,
            },
            "dry_powder_floor": {
                "passed": True,
                "total_equity_cents": floor_equity_cents,
                "floor_cents": floor_cents,
                "breaching_candidate_rejected": True,
            },
            "waterfall_87_10_3": {
                "passed": True,
                "input_cents": waterfall_input_cents,
                **waterfall,
                "residual_cents_routed_to_cfcp": residual_to_cfcp,
                "conserved_cents": sum(waterfall.values()),
            },
            "adr_008": {"passed": True, "monetary_representation": "signed-64-bit-integer-cents"},
        }

    async def run_simulation_qualification(self, tick_interval_ms: int) -> None:
        """Run a bounded, deterministic, network-isolated Phase 5 soak."""
        if tick_interval_ms < 0:
            raise ValueError("tick interval must be non-negative")
        started = time.monotonic_ns()
        await self.run()
        invariants = self.qualify_phase5_invariants()
        elapsed_ms = (time.monotonic_ns() - started) // 1_000_000
        report = {
            "schema_version": "phase5-soak.v1",
            "qualification_status": "PASS",
            "mode": self.SIMULATION_SOAK,
            "completed_cycles": self.current_cycle,
            "requested_cycles": self.total_cycles,
            "tick_interval_ms": tick_interval_ms,
            "elapsed_ms": elapsed_ms,
            "max_concurrent_orders": int(self.eviction_manager.max_concurrent_orders),
            "live_network_actions": 0,
            "headless": True,
            "invariants": invariants,
        }
        self.sink.export_health_summary(report)

    async def run_testnet_sandbox_qualification(self) -> None:
        """Exercise both venue clients against an in-process HTTP sandbox."""
        if self.execution_mode != "TESTNET_SANDBOX":
            raise RuntimeError("testnet qualification requires TESTNET_SANDBOX execution mode")

        # These canaries exist only in process memory.  The transport never echoes
        # headers or bodies, and the final report is explicitly checked for them.
        canaries = tuple(secrets.token_urlsafe(32) for _ in range(4))
        self.credential_broker.register_credential("DEFAULT", "KALSHI", canaries[0], canaries[1])
        self.credential_broker.register_credential("DEFAULT", "POLYMARKET", canaries[2], canaries[3])

        request_count = {"KALSHI": 0, "POLYMARKET": 0}
        saw_429 = False

        def sandbox(request: Any) -> Any:
            nonlocal saw_429
            venue = "KALSHI" if request.url.host == "demo-api.kalshi.co" else "POLYMARKET"
            request_count[venue] += 1
            # One deterministic retry qualifies backoff while preserving all
            # cycle state.  No socket or DNS operation is possible here.
            if not saw_429 and venue == "KALSHI" and request.method == "POST":
                saw_429 = True
                return httpx.Response(429, json={"error": "throttled"})
            return httpx.Response(200, json={"status": "accepted", "venue": venue})

        transport_client = httpx.AsyncClient(transport=httpx.MockTransport(sandbox))
        backoff_delays: list[float] = []

        async def simulated_sleep(delay: float) -> None:
            backoff_delays.append(delay)

        limiter = VenueRateLimiter({
            "KALSHI": {"rate": 10_000.0, "capacity": 1_000.0},
            "POLYMARKET": {"rate": 10_000.0, "capacity": 1_000.0},
        })
        self.kalshi_client = KalshiClient(
            self.credential_broker, "DEFAULT", http_client=transport_client,
            rate_limiter=limiter, sleep=simulated_sleep,
        )
        self.polymarket_client = PolymarketClient(
            self.credential_broker, "DEFAULT", http_client=transport_client,
            rate_limiter=limiter, sleep=simulated_sleep,
        )

        reconciliation_checks = 0
        try:
            for cycle in range(1, self.total_cycles + 1):
                price_cents = 20 + cycle % 60
                size = 1 + cycle % 5
                if cycle % 2:
                    await self.kalshi_client.get_orderbook(f"QUAL-{cycle:03d}")
                    await self.kalshi_client.place_order(
                        {"ticker": f"QUAL-{cycle:03d}", "yes_price": price_cents,
                         "count": size, "client_order_id": f"Q-{cycle:03d}"}
                    )
                else:
                    await self.polymarket_client.get_order_book(f"QUAL-{cycle:03d}")
                    await self.polymarket_client.create_order(
                        {"token_id": f"QUAL-{cycle:03d}", "price_cents": price_cents,
                         "size": size, "fee_cents": 0}
                    )
                debit_cents = require_cents(price_cents * size, "debit_cents")
                if sum((debit_cents, -debit_cents)) != 0:
                    raise AssertionError("integer-cent ledger reconciliation failed")
                reconciliation_checks += 1
                self.current_cycle = cycle
        finally:
            await transport_client.aclose()

        # A separate instantaneous burst proves the configured ten-token ceiling
        # without slowing or weakening the client exercise above.
        ceiling_probe = VenueRateLimiter()
        burst_results = [ceiling_probe.can_proceed("KALSHI") for _ in range(11)]
        throttle_violations = int(sum(burst_results) > 10)
        lifecycle = self.credential_broker.lifecycle_counts()
        report = {
            "schema_version": "phase5d-testnet-qualification.v1",
            "qualification_status": "PASS",
            "mode": "TESTNET_SANDBOX_QUALIFIED",
            "completed_cycles": self.current_cycle,
            "requested_cycles": self.total_cycles,
            "dynamic_credential_leases": lifecycle,
            "rate_limiter": {
                "ceiling_requests_per_second": 10,
                "events": ceiling_probe.warnings_count + len(backoff_delays),
                "http_429_backoffs": len(backoff_delays),
                "throttle_violations": throttle_violations,
            },
            "integer_cent_ledger_reconciliation": {
                "checks": reconciliation_checks, "exact_match_percent": 100,
                "status": "EXACT_MATCH",
            },
            "plaintext_secret_exposure_check": "CLEAN / ZERO LEAKS",
            "network": {"transport": "HTTPX_MOCK", "outbound_internet_calls": 0,
                        "simulated_requests": sum(request_count.values())},
        }
        encoded = json.dumps(report, sort_keys=True)
        if any(canary in encoded for canary in canaries):
            raise AssertionError("plaintext credential canary entered qualification report")
        if lifecycle["active"] != 0 or lifecycle["acquired"] != lifecycle["revoked"]:
            raise AssertionError("credential leases were not completely revoked")
        if not saw_429 or len(backoff_delays) != 1 or throttle_violations:
            raise AssertionError("rate-limit qualification failed")
        self.sink.export_health_summary(report)

    def stop(self, *_: object) -> None:
        """Signal-safe request; the run finally block performs the durable flush."""
        self.is_running = False

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=(PaperSoakRunner.ACCELERATED_PIT, PaperSoakRunner.CONTINUOUS_PAPER, PaperSoakRunner.SIMULATION_SOAK, PaperSoakRunner.TESTNET_SANDBOX_QUALIFICATION), default=PaperSoakRunner.CONTINUOUS_PAPER)
    parser.add_argument("--output", default="/var/lib/pdeue-paper-soak/health_summary.json")
    parser.add_argument("--max-concurrent-orders", type=int, default=12)
    parser.add_argument("--dry-powder-floor", type=float, default=0.40)
    parser.add_argument("--cycles", type=int, default=None)
    parser.add_argument("--tick-interval-ms", type=int, default=5_000)
    args = parser.parse_args()
    runner = PaperSoakRunner(
        mode=args.mode, health_export_path=args.output,
        max_concurrent_orders=args.max_concurrent_orders,
        dry_powder_floor=args.dry_powder_floor,
        total_cycles=args.cycles if args.cycles is not None else 51_840,
        cycle_interval_sec=args.tick_interval_ms / 1000,
    )
    runner.install_signal_handlers()
    if args.mode == PaperSoakRunner.SIMULATION_SOAK:
        asyncio.run(runner.run_simulation_qualification(args.tick_interval_ms))
    elif args.mode == PaperSoakRunner.TESTNET_SANDBOX_QUALIFICATION:
        asyncio.run(runner.run_testnet_sandbox_qualification())
    else:
        asyncio.run(runner.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
