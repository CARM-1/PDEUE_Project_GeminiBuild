import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.adapters.market_data_clients import MarketDataFeedAggregator
from app.domain.global_portfolio_dispatcher import GlobalPortfolioDispatcher
from app.domain.circuit_breaker import CircuitBreakerEngine
from app.domain.priority_eviction import PriorityEvictionManager

class AutonomousScanWorker:
    def __init__(
        self,
        aggregator: Optional[MarketDataFeedAggregator] = None,
        dispatcher: Optional[GlobalPortfolioDispatcher] = None,
        circuit_breaker: Optional[CircuitBreakerEngine] = None,
        eviction_manager: Optional[PriorityEvictionManager] = None,
        interval_seconds: float = 5.0,
        ledger: Optional[Any] = None,
    ):
        self.aggregator = aggregator or MarketDataFeedAggregator()
        self.dispatcher = dispatcher or GlobalPortfolioDispatcher()
        self.ledger = ledger
        if ledger is not None and hasattr(self.dispatcher, "ledger"):
            self.dispatcher.ledger = ledger
        self.circuit_breaker = circuit_breaker or CircuitBreakerEngine()
        self.eviction_manager = eviction_manager or PriorityEvictionManager()
        self.interval_seconds = interval_seconds
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self.stats = {
            'cycles_completed': 0,
            'total_contracts_scanned': 0,
            'total_orders_dispatched': 0,
            'total_evictions_executed': 0,
            'last_cycle_timestamp': None,
            'last_cycle_status': 'IDLE'
        }

    def run_single_cycle(self, tenant_id: str = 'tenant_daemon', account_id: str = 'acc_daemon') -> Dict[str, Any]:
        if not self.circuit_breaker.validate_execution_allowed():
            self.stats['last_cycle_status'] = 'HALTED_CIRCUIT_BREAKER'
            return {'status': 'HALTED', 'reason': 'CIRCUIT_BREAKER_TRIPPED'}
        board = self.aggregator.get_unified_board()
        contracts_count = len(board)
        if hasattr(self.dispatcher, 'dispatch_for_family_members') and getattr(getattr(self.dispatcher, 'ledger', None), 'members', {}):
            dispatch_res = self.dispatcher.dispatch_for_family_members(board_candidates=board)
        else:
            dispatch_res = self.dispatcher.dispatch_cross_category_board(tenant_id=tenant_id, account_id=account_id, board_candidates=board)
        self.stats['cycles_completed'] += 1
        self.stats['total_contracts_scanned'] += contracts_count
        self.stats['total_orders_dispatched'] += dispatch_res.get('dispatched_count', 0)
        self.stats['last_cycle_timestamp'] = datetime.now(timezone.utc).isoformat()
        self.stats['last_cycle_status'] = dispatch_res.get('status', 'COMPLETED')
        return {'cycle_number': self.stats['cycles_completed'], 'contracts_scanned': contracts_count, 'dispatch_result': dispatch_res, 'timestamp': self.stats['last_cycle_timestamp']}

    def evaluate_candidate_preemption(
        self,
        candidate: Dict[str, Any],
        total_equity_cents: int,
        currently_committed_cents: int
    ) -> Dict[str, Any]:
        """Evaluates an incoming candidate against resting limit orders for preemption."""
        return self.eviction_manager.evaluate_preemption(
            candidate=candidate,
            total_equity_cents=total_equity_cents,
            currently_committed_cents=currently_committed_cents
        )

    def execute_eviction(self, order_id: str, reason: str = "ALPHA_PREEMPTION") -> Dict[str, Any]:
        """Executes cancellation of an unfilled resting order to liberate capital."""
        evicted = self.eviction_manager.execute_eviction(order_id, reason=reason)
        self.stats['total_evictions_executed'] += 1
        return evicted

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _worker_loop(self):
        while self.is_running:
            try:
                self.run_single_cycle()
            except Exception as e:
                self.stats['last_cycle_status'] = f'ERROR: {str(e)}'
            time.sleep(self.interval_seconds)

    def get_telemetry(self) -> Dict[str, Any]:
        return {'is_running': self.is_running, 'interval_seconds': self.interval_seconds, 'stats': self.stats}
