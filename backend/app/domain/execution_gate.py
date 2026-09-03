import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

class ExecutionPolicyGate:
    ALLOWED_MODES = {"RESEARCH", "PAPER", "PRODUCTION"}
    def __init__(self, mode: str = "PAPER"):
        if mode not in self.ALLOWED_MODES:
            raise ValueError(f"Invalid mode: {mode}")
        self.mode = mode
        self.production_unlocked = False

    def unlock_production(self, authorization_token: str) -> bool:
        if authorization_token == "AUTH-PROD-GATED-SECRET":
            self.production_unlocked = True
            return True
        return False

    def authorize_execution_intent(self, intent: Dict[str, Any], account_reservation: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.mode == "RESEARCH":
            return {"authorized": False, "reason": "RESEARCH_MODE_NO_EXECUTION"}
        if self.mode == "PRODUCTION" and not self.production_unlocked:
            return {"authorized": False, "reason": "PRODUCTION_GATED_LOCKED"}
        if not account_reservation or not account_reservation.get("reserved", False):
            return {"authorized": False, "reason": "INSUFFICIENT_OR_UNRESERVED_CAPITAL"}
        if account_reservation.get("reserved_cents", 0) < intent.get("total_cost_cents", 0):
            return {"authorized": False, "reason": "RESERVATION_EXCEEDED"}
        return {"authorized": True, "mode": self.mode, "decision_packet_id": intent.get("decision_packet_id")}

class PreTradeValidator:
    def __init__(self):
        self.processed_idempotency_keys = set()

    def validate_order(self, order_payload: Dict[str, Any]) -> Dict[str, Any]:
        idem_key = order_payload.get("idempotency_key")
        if not idem_key:
            return {"valid": False, "reason": "MISSING_IDEMPOTENCY_KEY"}
        if idem_key in self.processed_idempotency_keys:
            return {"valid": False, "reason": "DUPLICATE_IDEMPOTENCY_KEY"}
        price = order_payload.get("price", 0.0)
        if price <= 0.0 or price >= 1.0:
            return {"valid": False, "reason": "PRICE_OUT_OF_BOUNDS"}
        quantity = order_payload.get("quantity", 0)
        if not isinstance(quantity, int) or quantity <= 0:
            return {"valid": False, "reason": "INVALID_QUANTITY"}
        side = order_payload.get("side")
        if side not in ("BUY", "SELL"):
            return {"valid": False, "reason": "INVALID_SIDE"}
        self.processed_idempotency_keys.add(idem_key)
        return {"valid": True, "order_id": f"ORD-{uuid.uuid4().hex[:8]}", "validated_at": datetime.now(timezone.utc).isoformat()}
