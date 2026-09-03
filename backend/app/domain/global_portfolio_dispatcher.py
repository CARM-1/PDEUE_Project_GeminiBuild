import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import json
from app.domain.cross_category_screener import CrossCategoryScreener
from app.domain.decision_packet import DecisionPacketBuilder
from app.domain.capital_ledger import CapitalLedger
from app.domain.execution_coordinator import ExecutionEnvelopeCoordinator
from app.db.models import DecisionPacketRecordModel, OrderRecordModel

class GlobalPortfolioDispatcher:
    def __init__(self, screener: Optional[CrossCategoryScreener] = None, packet_builder: Optional[DecisionPacketBuilder] = None, ledger: Optional[CapitalLedger] = None, coordinator: Optional[ExecutionEnvelopeCoordinator] = None, db_session = None, max_concurrent_orders: int = 3, max_portfolio_exposure_cents: int = 500000):
        self.screener = screener or CrossCategoryScreener()
        self.packet_builder = packet_builder or DecisionPacketBuilder()
        self.ledger = ledger or CapitalLedger(initial_balance_cents=10000000)
        self.coordinator = coordinator or ExecutionEnvelopeCoordinator(mode='PAPER')
        self.db_session = db_session
        self.max_concurrent_orders = max_concurrent_orders
        self.max_portfolio_exposure_cents = max_portfolio_exposure_cents
    def dispatch_cross_category_board(self, tenant_id: str, account_id: str, board_candidates: List[Dict[str, Any]], total_capital: float = 10000.0) -> Dict[str, Any]:
        screen_res = self.screener.screen_cross_category_board(board_candidates)
        leaderboard = screen_res.get('leaderboard', [])
        if not leaderboard:
            return {'status': 'ABSTAINED', 'reason': 'NO_ADMISSIBLE_OPPORTUNITIES', 'screen_summary': screen_res, 'dispatched_count': 0, 'dispatched_orders': [], 'total_allocated_cents': 0}
        dispatched = []
        total_allocated = 0
        for cand in leaderboard[:self.max_concurrent_orders]:
            prob = cand['model_probability']
            price = cand['entry_price']
            action = cand['recommended_action']
            target_prob = prob if action == 'BUY_YES' else round(1.0 - prob, 4)
            contract_id = cand['contract_id']
            venue = cand['venue']
            cat = cand['category']
            event_id = f'EVT-PORT-{cat}-{contract_id}'
            packet = self.packet_builder.build_decision_packet(event_id=event_id, raw_prob=target_prob, yes_ask=price, total_capital=total_capital, reliability_factor=1.0)
            stake_dollars = packet['capital_bid']['recommended_stake']
            stake_cents = int(round(stake_dollars * 100))
            if stake_cents <= 0 or packet['operating_mode'] == 'BLOCKED':
                continue
            if total_allocated + stake_cents > self.max_portfolio_exposure_cents:
                remaining_headroom = self.max_portfolio_exposure_cents - total_allocated
                if remaining_headroom < 100: continue
                stake_cents = remaining_headroom
                stake_dollars = stake_cents / 100.0
            res_id = f'RES-{uuid.uuid4().hex[:8]}'
            if not self.ledger.reserve_capital(res_id, stake_cents): continue
            qty = max(1, int(stake_dollars / price)) if price > 0 else 1
            idem_key = f'IDEM-PORT-{uuid.uuid4().hex[:12]}'
            order_intent = {'decision_packet_id': packet['packet_id'], 'contract_id': contract_id, 'side': 'BUY', 'price': price, 'quantity': qty, 'total_cost_cents': stake_cents, 'idempotency_key': idem_key}
            reservation = {'reserved': True, 'reserved_cents': stake_cents}
            exec_res = self.coordinator.execute_order_lifecycle(tenant_id=tenant_id, account_id=account_id, venue=venue, order_intent=order_intent, reservation=reservation)
            if exec_res.get('success'):
                total_allocated += stake_cents
                dispatched.append({'contract_id': contract_id, 'category': cat, 'venue': venue, 'action': action, 'allocated_cents': stake_cents, 'reservation_id': res_id, 'order_intent': order_intent, 'execution_result': exec_res})
                if self.db_session is not None:
                    db_packet = DecisionPacketRecordModel(packet_id=packet['packet_id'], tenant_id=tenant_id, event_id=event_id, operating_mode=packet.get('operating_mode', 'NORMAL'), model_probability=packet['underwriting']['calibrated_prob'], recommended_stake_cents=stake_cents, packet_payload=json.dumps(packet))
                    db_order = OrderRecordModel(order_id=f'ORD-{uuid.uuid4().hex[:8]}', tenant_id=tenant_id, contract_id=contract_id, venue=venue, side='BUY', price=price, quantity=qty, status='ROUTED', idempotency_key=idem_key)
                    self.db_session.add(db_packet); self.db_session.add(db_order); self.db_session.commit()
        return {'status': 'DISPATCHED' if dispatched else 'ABSTAINED', 'screen_summary': screen_res, 'dispatched_count': len(dispatched), 'dispatched_orders': dispatched, 'total_allocated_cents': total_allocated}
