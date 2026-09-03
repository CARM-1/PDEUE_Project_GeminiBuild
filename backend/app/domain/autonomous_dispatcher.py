import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.domain.opportunity_screener import OpportunityScreener
from app.domain.decision_packet import DecisionPacketBuilder
from app.domain.capital_ledger import CapitalLedger
from app.domain.execution_coordinator import ExecutionEnvelopeCoordinator

class AutonomousOpportunityDispatcher:
    def __init__(self, screener: Optional[OpportunityScreener] = None, packet_builder: Optional[DecisionPacketBuilder] = None, ledger: Optional[CapitalLedger] = None, coordinator: Optional[ExecutionEnvelopeCoordinator] = None):
        self.screener = screener or OpportunityScreener()
        self.packet_builder = packet_builder or DecisionPacketBuilder()
        self.ledger = ledger or CapitalLedger(initial_balance_cents=10000000)
        self.coordinator = coordinator or ExecutionEnvelopeCoordinator(mode='PAPER')
    def dispatch_weather_ladder(self, tenant_id: str, account_id: str, venue: str, event_id: str, ensemble_members: List[float], strike_ladder: List[Dict[str, Any]], station_id: str = 'KORD', total_capital: float = 10000.0) -> Dict[str, Any]:
        screen_res = self.screener.screen_weather_strike_ladder(ensemble_members=ensemble_members, strike_ladder=strike_ladder, station_id=station_id)
        top_pick = screen_res.get('top_pick')
        if not top_pick or top_pick.get('recommended_action') == 'PASS':
            return {'status': 'ABSTAINED', 'reason': 'NO_ADMISSIBLE_OPPORTUNITY', 'screen_summary': screen_res, 'dispatched_order': None}
        prob = top_pick['model_probability']
        price = top_pick['entry_price']
        action = top_pick['recommended_action']
        target_prob = prob if action == 'BUY_YES' else round(1.0 - prob, 4)
        packet = self.packet_builder.build_decision_packet(event_id=event_id, raw_prob=target_prob, yes_ask=price, total_capital=total_capital, reliability_factor=1.0)
        stake_dollars = packet['capital_bid']['recommended_stake']
        stake_cents = int(round(stake_dollars * 100))
        if stake_cents <= 0 or packet['operating_mode'] == 'BLOCKED':
            return {'status': 'ABSTAINED', 'reason': 'CAPITAL_ALLOCATION_ZERO', 'screen_summary': screen_res, 'decision_packet': packet, 'dispatched_order': None}
        res_id = f'RES-{uuid.uuid4().hex[:8]}'
        if not self.ledger.reserve_capital(res_id, stake_cents):
            return {'status': 'BLOCKED', 'reason': 'INSUFFICIENT_LEDGER_BALANCE', 'screen_summary': screen_res, 'decision_packet': packet, 'dispatched_order': None}
        qty = max(1, int(stake_dollars / price)) if price > 0 else 1
        order_intent = {'decision_packet_id': packet['packet_id'], 'contract_id': top_pick['contract_id'], 'side': 'BUY', 'price': price, 'quantity': qty, 'total_cost_cents': stake_cents, 'idempotency_key': f'IDEM-{uuid.uuid4().hex[:12]}'}
        reservation = {'reserved': True, 'reserved_cents': stake_cents}
        exec_res = self.coordinator.execute_order_lifecycle(tenant_id=tenant_id, account_id=account_id, venue=venue, order_intent=order_intent, reservation=reservation)
        return {'status': 'DISPATCHED' if exec_res.get('success') else 'EXECUTION_REJECTED', 'reservation_id': res_id, 'top_pick': top_pick, 'decision_packet': packet, 'order_intent': order_intent, 'execution_result': exec_res}
