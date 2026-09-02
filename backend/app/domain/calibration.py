from typing import Dict, Any, List
import math

class ProbabilityCalibrationEngine:
    def __init__(self):
        pass

    def calibrate_probability(self, raw_prob: float, reliability_factor: float = 1.0) -> float:
        bounded = max(0.001, min(0.999, raw_prob))
        logit = math.log(bounded / (1.0 - bounded))
        scaled_logit = logit * reliability_factor
        calibrated = 1.0 / (1.0 + math.exp(-scaled_logit))
        return round(calibrated, 4)

    def compute_brier_score(self, predictions: List[float], outcomes: List[int]) -> float:
        if not predictions or len(predictions) != len(outcomes):
            raise ValueError("Predictions and outcomes length mismatch")
        score = sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)
        return round(score, 4)
