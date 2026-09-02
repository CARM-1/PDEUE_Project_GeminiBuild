from typing import Dict, Any

class ContractMapper:
    def evaluate_resolution(self, contract: Dict[str, Any], observation: Dict[str, Any]) -> bool:
        metric = contract.get("metric")
        strike_val = contract.get("strike_value")
        payload_val = observation.get("payload", {}).get(metric)
        if payload_val is None or strike_val is None:
            return False
        return payload_val >= strike_val
