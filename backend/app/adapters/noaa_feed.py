"""
PDEUE NOAA ASOS Weather Observation Adapter
Point-in-Time validated airport weather station feed parser.
Enforces strict anti-lookahead knowledge cutoff controls.
"""
from typing import Dict, Any
from datetime import datetime

class NOAAASOSAdapter:
    """Automated Surface Observing System (ASOS) Feed Ingester."""
    def __init__(self):
        self.source = "NOAA_ASOS"

    def ingest_observation(
        self,
        station_id: str,
        temp_f: float,
        observed_at_iso: str,
        cutoff_iso: str
    ) -> Dict[str, Any]:
        """
        Parses station temperature and enforces strict PIT knowledge boundaries.
        Returns fail-closed admissibility status.
        """
        t_obs = datetime.fromisoformat(observed_at_iso.replace("Z", "+00:00"))
        t_cut = datetime.fromisoformat(cutoff_iso.replace("Z", "+00:00"))

        if t_obs > t_cut:
            return {
                "station_id": station_id,
                "admissible": False,
                "reason": "POST_CUTOFF_DATA_LEAKAGE",
                "observed_temp_f": temp_f,
                "observed_at": observed_at_iso,
                "cutoff": cutoff_iso,
                "freeze_condition_met": False
            }

        temp_c = round((temp_f - 32.0) * (5.0 / 9.0), 2)
        freeze_condition = temp_f <= 32.0

        return {
            "station_id": station_id,
            "admissible": True,
            "source": self.source,
            "observed_temp_f": temp_f,
            "observed_temp_c": temp_c,
            "freeze_condition_met": freeze_condition,
            "observed_at": observed_at_iso,
            "cutoff": cutoff_iso
        }
