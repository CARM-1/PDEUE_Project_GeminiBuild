import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

class PaperSessionManager:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def create_session(self, initial_capital_cents: int) -> Dict[str, Any]:
        session_id = f"PAPER-{uuid.uuid4().hex[:8]}"
        session = {
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "initial_capital_cents": initial_capital_cents,
            "available_capital_cents": initial_capital_cents,
            "executed_trades": [],
            "status": "ACTIVE"
        }
        self.sessions[session_id] = session
        return session

    def execute_paper_trade(self, session_id: str, contract_id: str, price: float, quantity: int) -> Dict[str, Any]:
        if session_id not in self.sessions:
            raise ValueError("Session not found")
        session = self.sessions[session_id]
        cost_cents = int(round(price * 100 * quantity))
        if cost_cents > session["available_capital_cents"]:
            return {"status": "REJECTED", "reason": "INSUFFICIENT_FUNDS"}
        session["available_capital_cents"] -= cost_cents
        trade = {
            "trade_id": f"TRD-{uuid.uuid4().hex[:6]}",
            "contract_id": contract_id,
            "price": price,
            "quantity": quantity,
            "cost_cents": cost_cents,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        session["executed_trades"].append(trade)
        return {"status": "EXECUTED", "trade": trade, "remaining_capital_cents": session["available_capital_cents"]}
