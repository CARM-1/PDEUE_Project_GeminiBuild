import threading, time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.domain.global_portfolio_dispatcher import GlobalPortfolioDispatcher
from app.adapters.market_data_clients import MarketDataFeedAggregator
from app.domain.circuit_breaker import CircuitBreakerEngine
from app.domain.position_book import PositionBook
from app.domain.capital_ledger import CapitalLedger

class AutonomousScanWorker:
    def __init__(self, dispatcher: Optional[GlobalPortfolioDispatcher] = None, feed_aggregator: Optional[MarketDataFeedAggregator] = None, circuit_breaker: Optional[CircuitBreakerEngine] = None, ledger: Optional[CapitalLedger] = None, position_book: Optional[PositionBook] = None, poll_interval_seconds: float = 5.0, tenant_id: str = 'tenant_daemon', account_id: str = 'acc_daemon'):
        self.ledger = ledger or (dispatcher.ledger if dispatcher else CapitalLedger())
        self.position_book = position_book or (dispatcher.position_book if dispatcher else PositionBook())
        self.dispatcher = dispatcher or GlobalPortfolioDispatcher(ledger=self.ledger, position_book=self.position_book)
        self.feed_aggregator = feed_aggregator or MarketDataFeedAggregator()
        self.circuit_breaker = circuit_breaker or CircuitBreakerEngine()
        self.poll_interval_seconds = poll_interval_seconds
        self.tenant_id = tenant_id
        self.account_id = account_id
        self.is_running: bool = False
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.cycles_completed: int = 0
        self.total_dispatched_count: int = 0
        self.last_cycle_timestamp: Optional[str] = None
        self.last_dispatched_count: int = 0

    def run_single_cycle(self) -> Dict[str, Any]:
        if self.circuit_breaker and not self.circuit_breaker.validate_execution_allowed():
            return {'status': 'BLOCKED', 'reason': f'CIRCUIT_BREAKER_TRIPPED: {self.circuit_breaker.trip_reason}', 'dispatched_count': 0, 'dispatched_orders': []}
        board = self.feed_aggregator.get_unified_board()
        if hasattr(self.position_book, 'update_market_prices'):
            self.position_book.update_market_prices(board)
        if hasattr(self.dispatcher, 'dispatch_for_family_members') and getattr(self.dispatcher.ledger, 'members', {}):
            res = self.dispatcher.dispatch_for_family_members(board_candidates=board)
        else:
            res = self.dispatcher.dispatch_cross_category_board(tenant_id=self.tenant_id, account_id=self.account_id, board_candidates=board)
        self.cycles_completed += 1
        self.last_cycle_timestamp = datetime.now(timezone.utc).isoformat()
        self.last_dispatched_count = res.get('dispatched_count', 0)
        self.total_dispatched_count += self.last_dispatched_count
        return {'status': res.get('status', 'COMPLETED'), 'cycle_number': self.cycles_completed, 'timestamp': self.last_cycle_timestamp, 'dispatched_count': self.last_dispatched_count, 'total_dispatched': self.total_dispatched_count, 'dispatch_summary': res}

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.run_single_cycle()
            time.sleep(self.poll_interval_seconds)

    def start(self) -> None:
        if self.is_running: return
        self.is_running = True
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._worker_thread.start()

    def stop(self) -> None:
        if not self.is_running: return
        self.is_running = False
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None
