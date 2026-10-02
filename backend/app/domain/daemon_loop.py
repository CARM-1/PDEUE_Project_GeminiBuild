"""Headless autonomous execution loop used by the worker and qualification soak."""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.domain.accounting_gateway import AccountingGateway
from app.domain.capital_ledger import CapitalLedger
from app.domain.position_book import PositionBook
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.settlement_reconciler import SettlementReconciler
from app.domain.venue_router import VenueOrderDispatcher


class AutonomousExecutionLoop:
    """Join scanning, admission, passive routing, settlement and accounting.

    All amounts crossing this boundary are integer cents.  A cycle settles the
    preceding cycle's simulated fills before admitting the next canonical feed.
    This makes capacity recycling deterministic without an external scheduler.
    """

    SLOT_CAPACITY = 12
    HIGH_WATERMARK_CENTS = 2_500_000

    def __init__(self, *, ledger: Optional[CapitalLedger] = None,
                 position_book: Optional[PositionBook] = None,
                 eviction_manager: Optional[PriorityEvictionManager] = None,
                 dispatcher: Optional[VenueOrderDispatcher] = None,
                 accounting_gateway: Optional[AccountingGateway] = None):
        self.ledger = ledger or CapitalLedger(initial_balance_cents=10_000)
        self.position_book = position_book or PositionBook()
        self.eviction_manager = eviction_manager or PriorityEvictionManager(
            max_concurrent_orders=self.SLOT_CAPACITY,
            preemption_alpha_threshold=0.0)
        self.accounting_gateway = accounting_gateway or AccountingGateway()
        self.dispatcher = dispatcher or VenueOrderDispatcher(
            position_book=self.position_book,
            available_capital_cents=self.ledger.balance_cents)
        self.reconciler = SettlementReconciler(
            position_book=self.position_book, ledger=self.ledger)
        self.pending_orders: Dict[str, Dict[str, Any]] = {}
        self.cycles_completed = 0
        self.orders_posted = 0
        self.orders_filled = 0
        self.evictions_executed = 0
        self.sweeps_emitted = 0
        self.total_distributed_cents = 0
        self.last_status = "IDLE"

    @staticmethod
    def canonical_feed(cycle: int = 0) -> List[Dict[str, Any]]:
        rows = (
            ("KX-MIA-FRZ", "KALSHI", "WEATHER", 28),
            ("KX-FED-RATE", "KALSHI", "MACRO", 34),
            ("POLY-NFL-CHAMP", "POLYMARKET", "SPORTS", 22),
            ("POLY-BTC-100K", "POLYMARKET", "CRYPTO", 31),
        )
        return [{"ticker": f"{ticker}-{cycle}", "contract_id": f"{ticker}-{cycle}",
                 "venue": venue, "category": category, "bid_cents": bid,
                 "ask_cents": bid + 3, "quantity": 1, "net_edge": 0.24 + i * 0.02,
                 "expiry_hours": 2} for i, (ticker, venue, category, bid) in enumerate(rows)]

    @staticmethod
    def _await(coro: Any) -> Any:
        """Run venue adapters from the deliberately synchronous daemon surface."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # PaperSoakRunner itself has an async sleep loop.  Keep the domain API
        # synchronous while isolating its short adapter coroutine in a thread.
        result: List[Any] = []
        failure: List[BaseException] = []
        def run() -> None:
            try:
                result.append(asyncio.run(coro))
            except BaseException as exc:  # propagated on the caller thread
                failure.append(exc)
        thread = threading.Thread(target=run)
        thread.start()
        thread.join()
        if failure:
            raise failure[0]
        return result[0]

    def total_equity_cents(self) -> int:
        member = sum(int(row["balance_cents"]) for row in self.ledger.members.values())
        exposed = sum(self.ledger.reservations.values()) + sum(self.ledger.commitments.values())
        return (self.ledger.balance_cents + member + self.ledger.central_family_pool_cents
                + self.ledger.founder_pool_cents + exposed)

    def dry_powder_floor_cents(self) -> int:
        return max(4_000, (self.total_equity_cents() * 40) // 100)

    def _settle_pending(self) -> List[Dict[str, Any]]:
        settlements = []
        for order_id, order in list(self.pending_orders.items()):
            reservation_id = order["reservation_id"]
            cost_cents = order["notional_cents"]
            quantity = order["quantity"]
            self.ledger.commit_reservation(reservation_id)
            payout_cents = quantity * 100  # deterministic winning paper fill
            split = self.reconciler.calculate_waterfall_split(payout_cents)
            self.ledger.credit_balance(split["scma_cents"])
            self.ledger.credit_central_family_pool(split["cfcp_cents"])
            self.ledger.credit_founder_pool(split["faep_cents"])
            self.ledger.commitments.pop(reservation_id, None)
            self.position_book.record_fill(
                order["contract_id"], order["venue"], order["category"], "BUY_YES",
                order["limit_price_cents"] / 100, quantity, cost_cents)
            closed = self.position_book.close_position(order["contract_id"], "YES", payout_cents)
            event = self.accounting_gateway.emit_settlement_event(
                order["contract_id"], "MASTER", payout_cents, split["scma_cents"],
                split["cfcp_cents"], split["faep_cents"])
            settlements.append({"order_id": order_id, "position": closed,
                                "distribution": split, "outbox_event": event})
            self.total_distributed_cents += sum(split.values())
            self.orders_filled += 1
            self.eviction_manager.mark_order_filled(order_id)
            self.eviction_manager.filled_orders.pop(order_id, None)
            self.dispatcher.routed_orders.pop(order_id, None)
            self.pending_orders.pop(order_id, None)
        self.dispatcher.available_capital_cents = self.ledger.balance_cents
        return settlements

    def dispatch_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        bid = candidate.get("bid_cents")
        quantity = candidate.get("quantity", 1)
        if not isinstance(bid, int) or isinstance(bid, bool) or not isinstance(quantity, int):
            raise TypeError("bid_cents and quantity must be integers")
        stake = (bid + 1) * quantity
        candidate = {**candidate, "proposed_stake_cents": stake}
        committed = sum(self.ledger.reservations.values()) + sum(self.ledger.commitments.values())
        decision = self.eviction_manager.evaluate_preemption(
            candidate, self.total_equity_cents(), committed)
        target = decision.get("eviction_target")
        if not decision["admitted"]:
            return {"status": "REJECTED", "reason": decision["reason"]}
        if target:
            evicted_id = target["order_id"]
            evicted = self.pending_orders.pop(evicted_id, None)
            self.eviction_manager.execute_eviction(evicted_id)
            self.dispatcher.routed_orders.pop(evicted_id, None)
            if evicted:
                self.ledger.release_reservation(evicted["reservation_id"])
            self.evictions_executed += 1
            self.dispatcher.available_capital_cents = self.ledger.balance_cents
        reservation_id = f"DAEMON-RES-{self.cycles_completed:06d}-{self.orders_posted:08d}"
        if not self.ledger.reserve_capital(reservation_id, stake):
            return {"status": "REJECTED", "reason": "INSUFFICIENT_CAPITAL"}
        self.dispatcher.available_capital_cents = self.ledger.balance_cents + stake
        routed = self._await(self.dispatcher.dispatch(candidate, stake))
        if routed.get("status") == "REJECTED":
            self.ledger.release_reservation(reservation_id)
            return routed
        order_id = routed["response"].get("order_id", routed["client_order_id"])
        routed.update({"reservation_id": reservation_id,
                       "category": candidate["category"], "net_edge": candidate["net_edge"]})
        self.pending_orders[order_id] = routed
        self.eviction_manager.register_resting_order(
            order_id=order_id, ticker=routed["contract_id"], domain=candidate["category"],
            net_edge=candidate["net_edge"], stake_cents=stake)
        self.orders_posted += 1
        return routed

    def run_cycle(self, feed: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
        settlements = self._settle_pending()
        candidates = list(feed) if feed is not None else self.canonical_feed(self.cycles_completed + 1)
        orders = [self.dispatch_candidate(candidate) for candidate in candidates]
        self.cycles_completed += 1
        before = len(self.accounting_gateway.event_outbox)
        # Resting maker reservations remain settled cash until fill.  Include
        # them when evaluating the high-watermark, but reserve only cash still
        # present after posting so balance reaches (and never crosses) the cap.
        settled_cash_cents = self.ledger.balance_cents + sum(self.ledger.reservations.values())
        sweep = self.accounting_gateway.emit_capital_sweep(settled_cash_cents)
        if sweep:
            # Reserve the emitted amount immediately so subsequent cycles cannot
            # emit the same dollars again while the outbox awaits harvesting.
            self.ledger.reserve_capital(
                f"CAPITAL-SWEEP-{sweep['sequence_id']:08d}",
                self.ledger.balance_cents - self.HIGH_WATERMARK_CENTS,
            )
            self.sweeps_emitted += 1
        self.last_status = "COMPLETED"
        return {"status": self.last_status, "cycle_number": self.cycles_completed,
                "contracts_scanned": len(candidates),
                "dispatched_orders": [o for o in orders if o.get("status") != "REJECTED"],
                "dispatched_count": sum(o.get("status") != "REJECTED" for o in orders),
                "rejected_count": sum(o.get("status") == "REJECTED" for o in orders),
                "settlements": settlements, "active_slots": len(self.pending_orders),
                "slot_capacity": self.SLOT_CAPACITY,
                "dry_powder_floor_cents": self.dry_powder_floor_cents(),
                "cash_balance_cents": self.ledger.balance_cents,
                "sweeps_emitted": self.sweeps_emitted,
                "timestamp": datetime.now(timezone.utc).isoformat()}

    def telemetry(self) -> Dict[str, Any]:
        return {"status": self.last_status, "cycles_completed": self.cycles_completed,
                "cycle_count": self.cycles_completed, "orders_posted": self.orders_posted,
                "orders_filled": self.orders_filled,
                "evictions_executed": self.evictions_executed,
                "active_maker_bids": len(self.pending_orders),
                "active_maker_orders": list(self.pending_orders.values()),
                "capital_sweeps_emitted": self.sweeps_emitted,
                "final_equity_cents": self.total_equity_cents(),
                "dry_powder_floor_cents": self.dry_powder_floor_cents()}
