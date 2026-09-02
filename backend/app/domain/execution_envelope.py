import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

class ExecutionEnvelope:
    def __init__(self, mode: str = "PAPER"):
        self.mode = mode
        self.kill_switch_active = False
        self.orders: Dict[str, Dict[str, Any]] = {}

    def trigger_kill_switch(self, reason: str) -> None:
        self.kill_switch_active = True

    def submit_order(self, contract_id: str, side: str, price: float, quantity: int, decision_packet_id: str) -> Dict[str, Any]:
        if self.kill_switch_active:
            return {"status": "BLOCKED", "reason": "KILL_SWITCH_ACTIVE"}
        if self.mode == "LIVE":
            return {"status": "BLOCKED", "reason": "LIVE_EXECUTION_UNAUTHORIZED"}
        order_id = f"ORD-{uuid.uuid4().hex[:8]}"
        order = {
            "order_id": order_id,
            "contract_id": contract_id,
            "side": side,
            "price": price,
            "quantity": quantity,
            "decision_packet_id": decision_packet_id,
            "mode": self.mode,
            "status": "FILLED" if self.mode == "PAPER" else "SUBMITTED",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.orders[order_id] = order
        return {"status": "SUCCESS", "order": order}
