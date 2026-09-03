import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.adapters.kalshi_adapter import KalshiVenueAdapter
from app.adapters.polymarket_adapter import PolymarketVenueAdapter
from app.domain.autonomous_dispatcher import AutonomousOpportunityDispatcher
from app.db.models import DecisionPacketRecordModel, OrderRecordModel

class MultiVenueCoordinator:
    def __init__(self, kalshi_adapter: Optional[KalshiVenueAdapter] = None, polymarket_adapter: Optional[PolymarketVenueAdapter] = None, dispatcher: Optional[AutonomousOpportunityDispatcher] = None, db_session = None):
        self.kalshi_adapter = kalshi_adapter or KalshiVenueAdapter()
        self.polymarket_adapter = polymarket_adapter or PolymarketVenueAdapter()
        self.dispatcher = dispatcher or AutonomousOpportunityDispatcher()
        self.db_session = db_session
    def process_and_dispatch_ladder(self, tenant_id: str, account_id: str, venue: str, category: str, raw_ladder: List[Dict[str, Any]], ensemble_members: List[float], event_id: str, station_id: str = 'KORD', total_capital: float = 10000.0) -> Dict[str, Any]:
        target_venue = venue.upper()
        if target_venue == 'KALSHI':
            normalized_ladder = self.kalshi_adapter.normalize_market_ladder(raw_ladder)
        elif target_venue == 'POLYMARKET':
            normalized_ladder = self.polymarket_adapter.normalize_market_ladder(raw_ladder)
        else:
            raise ValueError(f'Unsupported trading venue: {venue}')
        dispatch_res = self.dispatcher.dispatch_weather_ladder(tenant_id=tenant_id, account_id=account_id, venue=target_venue, event_id=event_id, ensemble_members=ensemble_members, strike_ladder=normalized_ladder, station_id=station_id, total_capital=total_capital)
        persisted = False
        if dispatch_res.get('status') == 'DISPATCHED' and self.db_session is not None:
            pkt = dispatch_res['decision_packet']
            intent = dispatch_res['order_intent']
            db_packet = DecisionPacketRecordModel(packet_id=pkt['packet_id'], tenant_id=tenant_id, event_id=event_id, operating_mode=pkt.get('operating_mode', 'NORMAL'), model_probability=pkt['underwriting']['calibrated_prob'], recommended_stake_cents=int(pkt['capital_bid']['recommended_stake'] * 100), packet_payload=json.dumps(pkt))
            db_order = OrderRecordModel(order_id=f'ORD-{uuid.uuid4().hex[:8]}', tenant_id=tenant_id, contract_id=intent['contract_id'], venue=target_venue, side=intent['side'], price=intent['price'], quantity=intent['quantity'], status='ROUTED', idempotency_key=intent['idempotency_key'])
            self.db_session.add(db_packet)
            self.db_session.add(db_order)
            self.db_session.commit()
            persisted = True
        return {'venue': target_venue, 'category': category, 'normalized_contracts_count': len(normalized_ladder), 'dispatch_result': dispatch_res, 'persisted': persisted}
