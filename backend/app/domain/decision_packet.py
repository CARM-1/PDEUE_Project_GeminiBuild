import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

class DecisionPacketBuilder:
    def build_packet(self, event_id: str, operating_mode: str, underwriting_res: Dict[str, Any], risk_res: Dict[str, Any], blocked_reasons: List[str] = None) -> Dict[str, Any]:
        return {
            "packet_id": str(uuid.uuid4()),
            "event_id": event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operating_mode": operating_mode,
            "underwriting": underwriting_res,
            "risk_assessment": risk_res,
            "blocked_reasons": blocked_reasons or []
        }
