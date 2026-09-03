import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

class EmergencyStopExecutor:
    """
    B7-EXE-08 Emergency Stop Executor.
    Cancels open orders, halts order router, and suspends execution across venues.
    """
    def __init__(self, order_router: Optional[Any] = None):
        self.order_router = order_router
        self.is_active: bool = False
        self.stop_history: List[Dict[str, Any]] = []

    def trigger_emergency_stop(self, actor_id: str, reason: str, affected_tenants: Optional[List[str]] = None) -> Dict[str, Any]:
        self.is_active = True
        if self.order_router and hasattr(self.order_router, 'set_emergency_stop'):
            self.order_router.set_emergency_stop(True)
        report_id = f'STOP-{uuid.uuid4().hex[:8].upper()}'
        record = {
            'report_id': report_id,
            'action': 'EMERGENCY_STOP_TRIGGERED',
            'actor_id': actor_id,
            'reason': reason,
            'affected_tenants': affected_tenants or ['ALL'],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        self.stop_history.append(record)
        return {'status': 'HALTED', 'report': record}

    def cancel_open_orders(self, active_orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cancelled = []
        now = datetime.now(timezone.utc).isoformat()
        for order in active_orders:
            cancelled.append({
                'order_id': order.get('order_id'),
                'status': 'CANCELLED_BY_EMERGENCY_STOP',
                'cancelled_at': now
            })
        return cancelled

    def lift_emergency_stop(self, actor_id: str, justification: str) -> Dict[str, Any]:
        self.is_active = False
        if self.order_router and hasattr(self.order_router, 'set_emergency_stop'):
            self.order_router.set_emergency_stop(False)
        record = {
            'action': 'EMERGENCY_STOP_LIFTED',
            'actor_id': actor_id,
            'justification': justification,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        self.stop_history.append(record)
        return {'status': 'RESUMED', 'report': record}
