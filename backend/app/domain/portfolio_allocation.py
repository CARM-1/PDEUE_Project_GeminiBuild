from typing import Dict, Any, Optional

class PortfolioAllocationEngine:
    def __init__(self, kelly_fraction: float = 0.25, max_position_pct: float = 0.10):
        self.kelly_fraction = kelly_fraction
        self.max_position_pct = max_position_pct

    def calculate_kelly_stake(self, calibrated_prob: float, yes_ask: float, total_capital: float) -> Dict[str, Any]:
        if yes_ask <= 0.0 or yes_ask >= 1.0 or calibrated_prob <= yes_ask:
            return {"recommended_stake": 0.0, "kelly_fraction_used": 0.0, "stake_pct": 0.0}
        
        b = (1.0 / yes_ask) - 1.0
        p = calibrated_prob
        q = 1.0 - p
        full_kelly = (b * p - q) / b if b > 0 else 0.0
        fractional_kelly = max(0.0, full_kelly * self.kelly_fraction)
        bounded_pct = min(fractional_kelly, self.max_position_pct)
        recommended_stake = round(bounded_pct * total_capital, 2)
        
        return {
            "recommended_stake": recommended_stake,
            "kelly_fraction_used": self.kelly_fraction,
            "stake_pct": round(bounded_pct, 4)
        }
