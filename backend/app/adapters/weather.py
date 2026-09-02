from datetime import datetime
from typing import Dict, Any

class NOAAAdapter:
    def parse_observation(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "evidence_id": raw_data["id"],
            "source": "NOAA_NWS",
            "published_at": raw_data["timestamp"],
            "payload": {"temperature_c": raw_data["temp"]}
        }
