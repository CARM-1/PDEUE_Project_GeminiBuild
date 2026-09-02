from typing import Dict, Any

class EventRiskEngine:
    def evaluate_risk(self, raw_edge: float, max_budget_cents: int) -> Dict[str, Any]:
        if raw_edge <= 0.05:
            return {"admissible": False, "reason": "EDGE_BELOW_THRESHOLD", "recommended_stake_cents": 0}
        recommended = int(max_budget_cents * min(raw_edge, 0.25))
        return {"admissible": True, "reason": "OK", "recommended_stake_cents": recommended}
