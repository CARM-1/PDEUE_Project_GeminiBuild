from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.domain.circuit_breaker import CircuitBreakerEngine
from app.domain.capital_ledger import CapitalLedger
from app.domain.cross_category_screener import CrossCategoryScreener
from app.adapters.market_data_clients import MarketDataFeedAggregator

class OperatorWorkspaceService:
    def __init__(self, circuit_breaker: Optional[CircuitBreakerEngine] = None, ledger: Optional[CapitalLedger] = None, screener: Optional[CrossCategoryScreener] = None, feed_aggregator: Optional[MarketDataFeedAggregator] = None):
        self.circuit_breaker = circuit_breaker or CircuitBreakerEngine()
        self.ledger = ledger or CapitalLedger(initial_balance_cents=10000000)
        self.screener = screener or CrossCategoryScreener()
        self.feed_aggregator = feed_aggregator or MarketDataFeedAggregator()

    def get_workspace_state(self, db_session = None) -> Dict[str, Any]:
        live_board = self.feed_aggregator.get_unified_board()
        screen_res = self.screener.screen_cross_category_board(live_board)
        total_reserved = sum(self.ledger.reservations.values())
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'operating_mode': 'HALTED' if self.circuit_breaker.is_tripped else 'PAPER',
            'circuit_breaker': {
                'is_tripped': self.circuit_breaker.is_tripped,
                'trip_reason': self.circuit_breaker.trip_reason,
                'tripped_at': self.circuit_breaker.tripped_at
            },
            'ledger': {
                'available_balance_cents': self.ledger.balance_cents,
                'reserved_cents': total_reserved,
                'total_capital_cents': self.ledger.balance_cents + total_reserved
            },
            'opportunities': screen_res.get('leaderboard', []),
            'audit_events_count': len(self.circuit_breaker.trip_history)
        }

    def trigger_emergency_kill_switch(self, actor_id: str, reason: str) -> Dict[str, Any]:
        return self.circuit_breaker.trip(reason=reason, actor_id=actor_id)
