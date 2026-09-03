import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Set

class ModeController:
    VALID_MODES: Set[str] = {"RESEARCH", "REPLAY", "PAPER", "SHADOW", "PRODUCTION", "HALTED"}

    ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
        "RESEARCH": {"REPLAY", "PAPER", "HALTED"},
        "REPLAY": {"RESEARCH", "PAPER", "HALTED"},
        "PAPER": {"RESEARCH", "SHADOW", "HALTED"},
        "SHADOW": {"PAPER", "PRODUCTION", "HALTED"},
        "PRODUCTION": {"HALTED"},
        "HALTED": {"RESEARCH", "REPLAY", "PAPER"}
    }

    def __init__(self, initial_mode: str = "RESEARCH"):
        if initial_mode not in self.VALID_MODES:
            raise ValueError(f"Invalid initial mode: {initial_mode}")
        self.current_mode: str = initial_mode
        self.history: List[Dict[str, Any]] = []

    def transition_to(self, target_mode: str, actor_id: str, justification: str) -> Dict[str, Any]:
        if target_mode not in self.VALID_MODES:
            raise ValueError(f"Target mode {target_mode} is not recognized")
        allowed = self.ALLOWED_TRANSITIONS.get(self.current_mode, set())
        if target_mode not in allowed:
            raise PermissionError(f"Illegal transition from {self.current_mode} to {target_mode}")
        
        record = {
            "transition_id": str(uuid.uuid4()),
            "prior_mode": self.current_mode,
            "new_mode": target_mode,
            "actor_id": actor_id,
            "justification": justification,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.current_mode = target_mode
        self.history.append(record)
        return record

    def can_execute_orders(self) -> bool:
        return self.current_mode in {"PAPER", "PRODUCTION"}

    def can_ingest_live_data(self) -> bool:
        return self.current_mode in {"PAPER", "SHADOW", "PRODUCTION"}
