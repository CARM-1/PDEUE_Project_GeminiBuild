from typing import List, Dict, Any

class WeatherProbabilityEngine:
    def compute_probability(self, evidence_items: List[Dict[str, Any]], strike_temp_c: float) -> float:
        if not evidence_items:
            return 0.0
        obs_temps = [
            item["payload"]["temperature_c"]
            for item in evidence_items
            if "temperature_c" in item.get("payload", {})
        ]
        if not obs_temps:
            return 0.0
        exceeding_count = sum(1 for temp in obs_temps if temp >= strike_temp_c)
        return round(exceeding_count / len(obs_temps), 4)
