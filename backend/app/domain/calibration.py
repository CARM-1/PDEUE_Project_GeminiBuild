from typing import Dict, Any, List, Optional
import math

class ProbabilityCalibrationEngine:
    def __init__(self, reliability_factor: float = 1.0):
        self.reliability_factor = reliability_factor

    def calibrate_probability(self, raw_prob: float, reliability_factor: Optional[float] = None) -> float:
        rf = reliability_factor if reliability_factor is not None else self.reliability_factor
        bounded = max(0.001, min(0.999, raw_prob))
        logit = math.log(bounded / (1.0 - bounded))
        scaled_logit = logit * rf
        calibrated = 1.0 / (1.0 + math.exp(-scaled_logit))
        return round(calibrated, 4)

    def calibrate(self, raw_prob: float, reliability_factor: Optional[float] = None) -> float:
        return self.calibrate_probability(raw_prob, reliability_factor)

    def compute_brier_score(self, predictions: List[float], outcomes: List[int]) -> float:
        if not predictions or len(predictions) != len(outcomes):
            raise ValueError("Predictions and outcomes length mismatch")
        score = sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)
        return round(score, 4)

ProbabilityCalibrator = ProbabilityCalibrationEngine
