from typing import Dict, Any, Optional

class StationBiasCalibrator:
    KNOWN_STATION_BIASES: Dict[str, float] = {
        'KORD': 0.85,
        'KDEN': -0.40,
        'KNYC': 1.10,
        'KMIA': 0.50
    }
    def __init__(self, custom_biases: Optional[Dict[str, float]] = None):
        self.biases = dict(self.KNOWN_STATION_BIASES)
        if custom_biases:
            self.biases.update(custom_biases)

    def calibrate_observation(self, station_id: str, raw_metric_value: float) -> Dict[str, Any]:
        offset = self.biases.get(station_id.upper(), 0.0)
        calibrated_value = round(raw_metric_value + offset, 4)
        return {
            'station_id': station_id.upper(),
            'raw_value': raw_metric_value,
            'bias_offset': offset,
            'calibrated_value': calibrated_value
        }
