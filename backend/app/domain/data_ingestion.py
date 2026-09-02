from typing import Dict, Any, Optional
from datetime import datetime, timezone
import jsonschema

class DataIngestionEngine:
    def __init__(self):
        self.records = []

    def ingest_noaa_observation(self, station_id: str, temperature_c: float, timestamp: str) -> Dict[str, Any]:
        record = {
            "source": "NOAA",
            "station_id": station_id,
            "observation": {"temperature_c": temperature_c},
            "observation_time": timestamp,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "validated": True
        }
        self.records.append(record)
        return record

    def filter_point_in_time(self, cutoff_iso: str) -> list:
        cutoff = datetime.fromisoformat(cutoff_iso.replace("Z", "+00:00"))
        valid_records = []
        for r in self.records:
            r_time = datetime.fromisoformat(r["observation_time"].replace("Z", "+00:00"))
            if r_time <= cutoff:
                valid_records.append(r)
        return valid_records
