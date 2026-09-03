from typing import Dict, Any, Optional, List
from app.domain.execution_gate import ExecutionPolicyGate, PreTradeValidator
from app.domain.order_router import OrderRouter
from app.domain.reconciliation_engine import ReconciliationEngine
from app.domain.position_service import PositionStateService
from app.domain.settlement_interface import SettlementInterface
from app.domain.credential_broker import VenueCredentialBroker
from app.domain.emergency_stop import EmergencyStopExecutor

class ExecutionEnvelopeCoordinator:
    """
    Wave 8 Unified Execution Envelope Coordinator.
    Binds B7-EXE-01 through B7-EXE-08 into a fail-closed execution lifecycle.
    """
    def __init__(self, mode: str = 'PAPER'):
        self.policy_gate = ExecutionPolicyGate(mode=mode)
        self.validator = PreTradeValidator()
        self.order_router = OrderRouter()
        self.reconciliation_engine = ReconciliationEngine()
        self.position_service = PositionStateService()
        self.settlement_interface = SettlementInterface()
        self.credential_broker = VenueCredentialBroker()
        self.emergency_stop = EmergencyStopExecutor(order_router=self.order_router)

    def execute_order_lifecycle(
        self,
        tenant_id: str,
        account_id: str,
        venue: str,
        order_intent: Dict[str, Any],
        reservation: Dict[str, Any]
    ) -> Dict[str, Any]:
        if self.emergency_stop.is_active:
            return {'success': False, 'stage': 'EMERGENCY_STOP', 'reason': 'EMERGENCY_STOP_ACTIVE'}
        auth_res = self.policy_gate.authorize_execution_intent(order_intent, reservation)
        if not auth_res.get('authorized', False):
            return {'success': False, 'stage': 'POLICY_GATE', 'reason': auth_res.get('reason')}
        val_res = self.validator.validate_order(order_intent)
        if not val_res.get('valid', False):
            return {'success': False, 'stage': 'PRE_TRADE_VALIDATION', 'reason': val_res.get('reason')}
        order_payload = {**order_intent, **val_res, 'tenant_id': tenant_id}
        route_res = self.order_router.route_order(order_payload, venue=venue)
        if route_res.get('status') != 'SUCCESS':
            return {'success': False, 'stage': 'ROUTER', 'reason': route_res.get('reason')}
        return {
            'success': True,
            'stage': 'ROUTED',
            'order_id': route_res.get('order_id'),
            'routed_payload': route_res.get('payload')
        }
