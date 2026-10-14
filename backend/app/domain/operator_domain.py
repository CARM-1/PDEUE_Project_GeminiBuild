from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid

class OperatorControlEngine:
    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.audit_log: List[Dict[str, Any]] = []

    def start_paper_session(self, tenant_id: str, initial_capital: float = 100000.0) -> Dict[str, Any]:
        session_id = str(uuid.uuid4())
        session = {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "status": "ACTIVE",
            "initial_capital": initial_capital,
            "current_balance": initial_capital,
            "started_at": datetime.now(timezone.utc).isoformat()
        }
        self.active_sessions[session_id] = session
        self.log_audit_event(tenant_id, "SESSION_STARTED", {"session_id": session_id})
        return session

    def log_audit_event(self, tenant_id: str, action: str, details: Dict[str, Any]) -> Dict[str, Any]:
        entry = {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "action": action,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.audit_log.append(entry)
        return entry
