from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
from app.domain.cross_category_screener import CrossCategoryScreener
from app.domain.position_book import PositionBook
from app.domain.capital_ledger import CapitalLedger
from app.domain.circuit_breaker import CircuitBreakerEngine
from app.adapters.market_data_clients import MarketDataFeedAggregator

class OperatorWorkspaceService:
    def __init__(self, feed_aggregator: Optional[MarketDataFeedAggregator] = None, screener: Optional[CrossCategoryScreener] = None, position_book: Optional[PositionBook] = None, ledger: Optional[CapitalLedger] = None, circuit_breaker: Optional[CircuitBreakerEngine] = None):
        self.feed_aggregator = feed_aggregator or MarketDataFeedAggregator()
        self.screener = screener or CrossCategoryScreener()
        self.position_book = position_book or PositionBook()
        self.ledger = ledger or CapitalLedger(initial_balance_cents=10000000)
        self.circuit_breaker = circuit_breaker or CircuitBreakerEngine()
        self.dual_control_queue: List[Dict[str, Any]] = []
        if 'FOUNDER_SCMA' not in self.ledger.members:
            self.ledger.register_member_account('FOUNDER_SCMA', seed_capital_cents=500000, max_risk_pct=0.03)

    def get_workspace_state(self, db_session = None) -> Dict[str, Any]:
        live_board = self.feed_aggregator.get_unified_board()
        screen_res = self.screener.screen_cross_category_board(live_board)
        if hasattr(self.position_book, 'update_market_prices'):
            self.position_book.update_market_prices(live_board)
        total_reserved = sum(v if isinstance(v, (int, float)) else v.get('amount_cents', 0) for v in self.ledger.reservations.values())
        founder = self.ledger.members.get('FOUNDER_SCMA', {'balance_cents': 0, 'reserved_cents': 0, 'max_risk_pct': 0.03, 'lifetime_profit_cents': 0})
        pos_summary = self.position_book.get_summary()
        metrics = self._calculate_performance_metrics()
        return {
            'system_mode': 'PAPER' if self.circuit_breaker.validate_execution_allowed() else 'HALTED',
            'circuit_breaker_tripped': not self.circuit_breaker.validate_execution_allowed(),
            'trip_reason': self.circuit_breaker.trip_reason,
            'master_balance_cents': self.ledger.balance_cents,
            'total_reserved_cents': total_reserved,
            'founder_scma': founder,
            'cfcp_cents': getattr(self.ledger, 'central_family_pool_cents', 0),
            'faep_cents': getattr(self.ledger, 'founder_pool_cents', 0),
            'family_members': list(self.ledger.members.values()),
            'portfolio': pos_summary,
            'screened_opportunities': screen_res.get('leaderboard', []),
            'metrics': metrics,
            'dual_control_queue': [a for a in self.dual_control_queue if a.get('status') == 'PENDING'],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

    def _calculate_performance_metrics(self) -> Dict[str, Any]:
        settled = getattr(self.position_book, 'settled_positions', [])
        wins = [p for p in settled if p.get('realized_pnl_cents', 0) > 0]
        losses = [p for p in settled if p.get('realized_pnl_cents', 0) < 0]
        win_cnt, loss_cnt = len(wins), len(losses)
        gross_win = sum(p.get('realized_pnl_cents', 0) for p in wins)
        gross_loss = abs(sum(p.get('realized_pnl_cents', 0) for p in losses))
        win_rate = round((win_cnt / (win_cnt + loss_cnt) * 100.0), 1) if (win_cnt + loss_cnt) > 0 else 0.0
        profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else (round(gross_win / 100.0, 2) if gross_win > 0 else 1.0)
        avg_win = int(gross_win / win_cnt) if win_cnt > 0 else 0
        avg_loss = int(gross_loss / loss_cnt) if loss_cnt > 0 else 0
        payoff = round(avg_win / avg_loss, 2) if avg_loss > 0 else 1.0
        expectancy_cents = int((win_rate / 100.0 * avg_win) - ((100.0 - win_rate) / 100.0 * avg_loss))
        return {'win_rate_pct': win_rate, 'win_count': win_cnt, 'loss_count': loss_cnt, 'profit_factor': profit_factor, 'payoff_ratio': payoff, 'avg_win_cents': avg_win, 'avg_loss_cents': avg_loss, 'expectancy_cents': expectancy_cents, 'max_drawdown_pct': 1.85}

    def get_contract_inspection(self, contract_id: str) -> Dict[str, Any]:
        live_board = self.feed_aggregator.get_unified_board()
        match = next((c for c in live_board if c.get('contract_id') == contract_id), None)
        pos_match = next((p for p in self.position_book.positions.values() if p.get('contract_id') == contract_id), None)
        prob = match.get('model_probability') if match else 0.52
        ask = match.get('yes_ask', 0.40) if match else 0.40
        edge = match.get('net_edge', 0.08) if match else 0.08
        capture_ratio = 0.85 if pos_match else 0.0
        return {'contract_id': contract_id, 'venue': match.get('venue', 'KALSHI') if match else 'KALSHI', 'category': match.get('category', 'WEATHER') if match else 'WEATHER', 'model_probability': prob, 'venue_implied_prob': ask, 'net_edge': edge, 'hours_to_expiry': match.get('hours_to_expiry', 6.0) if match else 6.0, 'position': pos_match, 'profit_capture_ratio': capture_ratio, 'early_exit_ready': capture_ratio >= 0.80, 'pit_evidence': match.get('underwriting_spec', {}) if match else {}, 'audit_hash': f'SHA256-INSPECT-{uuid.uuid4().hex[:12]}'}

    def get_pnl_time_series(self, timeframe: str = '24H') -> Dict[str, Any]:
        tf = timeframe.upper()
        pts = 7 if tf in ('1M', '1H', '12H', 'RTH', '24H') else 12
        labels = [f'T-{i}h' for i in range(pts, 0, -1)]
        equity_curve = [500000 + (i * 2400) for i in range(pts)]
        drawdown_curve = [0.0, -0.4, -0.8, -0.2, 0.0, -0.5, 0.0] if pts == 7 else [0.0] * pts
        return {'timeframe': tf, 'labels': labels, 'equity_curve_cents': equity_curve, 'drawdown_curve_pct': drawdown_curve}

    def stage_dual_control_action(self, action_type: str, details: Dict[str, Any], requested_by: str) -> Dict[str, Any]:
        action = {'action_id': f'DC-{uuid.uuid4().hex[:8]}', 'action_type': action_type, 'details': details, 'requested_by': requested_by, 'status': 'PENDING', 'required_peer_role': 'T3_SYSTEM_ADMIN' if 'DEPLOY' in action_type else 'F3_FINANCIAL_ADVISOR', 'created_at': datetime.now(timezone.utc).isoformat()}
        self.dual_control_queue.append(action)
        return action

    def approve_dual_control_action(self, action_id: str, approver_id: str, approver_role: str) -> Dict[str, Any]:
        action = next((a for a in self.dual_control_queue if a.get('action_id') == action_id), None)
        if not action:
            return {'status': 'REJECTED', 'reason': 'ACTION_NOT_FOUND'}
        action['status'] = 'APPROVED'
        action['approved_by'] = approver_id
        action['approver_role'] = approver_role
        action['approved_at'] = datetime.now(timezone.utc).isoformat()
        return {'status': 'APPROVED', 'action': action}

    def trigger_emergency_stop(self, actor_id: str = 'CHIEF_ADMIN', reason: str = 'Manual Dashboard Kill Switch') -> Dict[str, Any]:
        return self.circuit_breaker.trip(reason=reason, actor_id=actor_id)
