from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.domain.circuit_breaker import CircuitBreakerEngine
from app.domain.capital_ledger import CapitalLedger
from app.domain.cross_category_screener import CrossCategoryScreener

class OperatorWorkspaceService:
    def __init__(self, circuit_breaker: Optional[CircuitBreakerEngine] = None, ledger: Optional[CapitalLedger] = None, screener: Optional[CrossCategoryScreener] = None):
        self.circuit_breaker = circuit_breaker or CircuitBreakerEngine()
        self.ledger = ledger or CapitalLedger(initial_balance_cents=10000000)
        self.screener = screener or CrossCategoryScreener()

    def get_workspace_state(self, db_session = None) -> Dict[str, Any]:
        board_sample = [
            {'contract_id': 'KX-ORD-26', 'category': 'WEATHER', 'venue': 'KALSHI', 'yes_bid': 0.08, 'yes_ask': 0.12, 'underwriting_spec': {'strike_temp_c': 26.0, 'ensemble_members': [24.0, 24.5, 25.0, 25.5, 25.0], 'station_id': 'KORD'}},
            {'contract_id': 'KX-CPI-3.0', 'category': 'MACROECONOMIC', 'venue': 'KALSHI', 'yes_bid': 0.55, 'yes_ask': 0.60, 'underwriting_spec': {'threshold': 3.0, 'evidence': [{'source': 'BLS', 'value': 3.40, 'available_at': '2026-09-01T12:00:00Z'}]}}
        ]
        screen_res = self.screener.screen_cross_category_board(board_sample)
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
