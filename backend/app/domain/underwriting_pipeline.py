from datetime import datetime
from typing import Dict, Any, List
from app.domain.pit_selector import PITSelector
from app.domain.weather_engine import WeatherProbabilityEngine
from app.domain.market_comparator import MarketComparator

class UnderwritingPipeline:
    def run_underwriting(self, cutoff: datetime, evidence: List[Dict[str, Any]], market_snapshot: Dict[str, Any], strike_temp: float) -> Dict[str, Any]:
        pit = PITSelector(cutoff)
        admissible = pit.filter_admissible_evidence(evidence)
        engine = WeatherProbabilityEngine()
        model_prob = engine.compute_probability(admissible, strike_temp)
        comparator = MarketComparator()
        edge_metrics = comparator.calculate_edge(model_prob, market_snapshot)
        return {
            "admissible_count": len(admissible),
            "model_probability": model_prob,
            "edge_metrics": edge_metrics
        }
