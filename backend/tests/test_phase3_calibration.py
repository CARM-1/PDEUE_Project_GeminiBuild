from app.domain.calibration import ProbabilityCalibrationEngine

def test_probability_calibration_and_brier():
    engine = ProbabilityCalibrationEngine()
    calibrated = engine.calibrate_probability(0.75, reliability_factor=0.9)
    assert 0.70 <= calibrated <= 0.75
    score = engine.compute_brier_score([0.8, 0.2, 0.7], [1, 0, 1])
    assert score == round(((0.8-1)**2 + (0.2-0)**2 + (0.7-1)**2)/3, 4)
