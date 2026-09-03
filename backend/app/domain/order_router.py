import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class OrderRouter:
    def __init__(self):
        self.routed_orders: Dict[str, Dict[str, Any]] = {}
        self.emergency_stop: bool = False

    def set_emergency_stop(self, stop_active: bool) -> None:
        self.emergency_stop = stop_active

    def route_order(self, validated_order: Dict[str, Any], venue: str = 'PAPER_SIMULATOR') -> Dict[str, Any]:
        if self.emergency_stop:
            return {'status': 'REJECTED', 'order_id': None, 'reason': 'EMERGENCY_STOP_ACTIVE', 'timestamp': datetime.now(timezone.utc).isoformat()}
        is_valid = validated_order.get('is_valid', False) or validated_order.get('valid', False)
        if not is_valid:
            return {'status': 'REJECTED', 'order_id': None, 'reason': 'INVALID_PRE_TRADE_ORDER', 'timestamp': datetime.now(timezone.utc).isoformat()}
        order_id = validated_order.get('order_id') or f'ORD-{uuid.uuid4().hex[:8].upper()}'
        record = {
            'order_id': order_id,
            'tenant_id': validated_order.get('tenant_id', 'default_tenant'),
            'venue': venue.upper(),
            'contract_id': validated_order.get('contract_id', 'UNKNOWN'),
            'side': validated_order.get('side', 'BUY'),
            'price': validated_order.get('price', 0.0),
            'quantity': validated_order.get('quantity', 0),
            'idempotency_key': validated_order.get('idempotency_key'),
            'status': 'ROUTED',
            'routed_at': datetime.now(timezone.utc).isoformat()
        }
        self.routed_orders[order_id] = record
        return {'status': 'SUCCESS', 'order_id': order_id, 'payload': record}
