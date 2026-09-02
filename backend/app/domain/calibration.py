class ProbabilityCalibrator:
    def calibrate(self, raw_prob: float) -> float:
        return round(max(0.0, min(1.0, raw_prob * 0.98 + 0.01)), 4)
