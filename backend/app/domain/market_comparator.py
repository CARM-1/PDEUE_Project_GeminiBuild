from typing import Dict, Any

class MarketComparator:
    def calculate_edge(self, model_prob: float, market_snapshot: Dict[str, Any]) -> Dict[str, float]:
        yes_ask = market_snapshot.get("yes_ask", 1.0)
        yes_bid = market_snapshot.get("yes_bid", 0.0)
        implied_prob = (yes_ask + yes_bid) / 2.0
        edge = model_prob - implied_prob
        return {
            "implied_probability": round(implied_prob, 4),
            "raw_edge": round(edge, 4),
            "buy_yes_advantage": round(model_prob - yes_ask, 4),
            "buy_no_advantage": round((1.0 - model_prob) - (1.0 - yes_bid), 4)
        }
