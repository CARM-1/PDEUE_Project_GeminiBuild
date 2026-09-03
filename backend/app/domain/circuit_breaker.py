import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

class CircuitBreakerEngine:
    def __init__(self):
        self.is_tripped: bool = False
        self.trip_reason: Optional[str] = None
        self.tripped_at: Optional[str] = None
        self.tripped_by: Optional[str] = None
        self.trip_history: List[Dict[str, Any]] = []

    def trip(self, reason: str, actor_id: str) -> Dict[str, Any]:
        self.is_tripped = True
        self.trip_reason = reason
        self.tripped_at = datetime.now(timezone.utc).isoformat()
        self.tripped_by = actor_id
        record = {
            "event_id": str(uuid.uuid4()),
            "action": "CIRCUIT_BREAKER_TRIPPED",
            "reason": reason,
            "actor_id": actor_id,
            "timestamp": self.tripped_at
        }
        self.trip_history.append(record)
        return record

    def reset(self, actor_id: str, justification: str) -> Dict[str, Any]:
        record = {
            "event_id": str(uuid.uuid4()),
            "action": "CIRCUIT_BREAKER_RESET",
            "prior_reason": self.trip_reason,
            "actor_id": actor_id,
            "justification": justification,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.is_tripped = False
        self.trip_reason = None
        self.tripped_at = None
        self.tripped_by = None
        self.trip_history.append(record)
        return record

    def validate_execution_allowed(self) -> bool:
        return not self.is_tripped
