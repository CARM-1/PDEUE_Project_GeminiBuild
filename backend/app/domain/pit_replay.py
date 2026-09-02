from typing import Dict, Any, List, Optional
from app.domain.calibration import ProbabilityCalibrationEngine

class PITReplayEngine:
    def __init__(self):
        self.calibrator = ProbabilityCalibrationEngine()

    def reconstruct_pit_snapshot(self, event_id: str, cutoff_timestamp: str, raw_observations: List[Dict[str, Any]]) -> Dict[str, Any]:
        valid_obs = [obs for obs in raw_observations if obs.get("timestamp", "") <= cutoff_timestamp]
        latest_obs = valid_obs[-1] if valid_obs else None
        return {
            "event_id": event_id,
            "cutoff_timestamp": cutoff_timestamp,
            "observation_count": len(valid_obs),
            "active_observation": latest_obs
        }

    def run_backtest_simulation(self, historical_ticks: List[Dict[str, Any]], reliability_factor: float = 1.0) -> Dict[str, Any]:
        total_trades = 0
        total_edge = 0.0
        predictions = []
        outcomes = []
        for tick in historical_ticks:
            raw_prob = tick.get("raw_prob", 0.5)
            calibrated = self.calibrator.calibrate_probability(raw_prob, reliability_factor)
            ask = tick.get("yes_ask", 0.5)
            edge = calibrated - ask
            if edge > 0.05:
                total_trades += 1
                total_edge += edge
                predictions.append(calibrated)
                outcomes.append(tick.get("outcome", 1))
        brier = self.calibrator.compute_brier_score(predictions, outcomes) if predictions else 0.0
        return {
            "total_trades": total_trades,
            "cumulative_edge": round(total_edge, 4),
            "brier_score": brier
        }
