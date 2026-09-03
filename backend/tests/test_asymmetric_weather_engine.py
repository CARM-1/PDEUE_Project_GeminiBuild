from app.domain.station_bias_calibrator import StationBiasCalibrator
from app.domain.advanced_weather_engine import AdvancedWeatherEngine

def test_station_bias_calibrator():
    calibrator = StationBiasCalibrator()
    res_kord = calibrator.calibrate_observation('KORD', 25.0)
    assert res_kord['calibrated_value'] == 25.85
    assert res_kord['bias_offset'] == 0.85
    res_unknown = calibrator.calibrate_observation('KXYZ', 20.0)
    assert res_unknown['calibrated_value'] == 20.0
    assert res_unknown['bias_offset'] == 0.0

def test_advanced_weather_engine_ngr_distribution():
    engine = AdvancedWeatherEngine()
    ensemble = [24.0, 25.0, 26.0, 25.0, 24.5]
    dist = engine.compute_ngr_distribution(ensemble, station_id='KORD')
    assert dist['mu'] == 25.75
    assert dist['sigma'] > 0.0

def test_exceedance_probability_gaussian():
    engine = AdvancedWeatherEngine()
    ensemble = [20.0, 20.0, 20.0, 20.0]
    res = engine.calculate_exceedance_probability(strike_temp_c=20.0, ensemble_members=ensemble, station_id=None, use_evt_tail=False)
    assert res['method'] == 'NGR_GAUSSIAN'
    assert res['probability'] == 0.5

def test_exceedance_probability_evt_tail():
    engine = AdvancedWeatherEngine()
    ensemble = [19.0, 20.0, 21.0, 20.0, 20.0]
    res = engine.calculate_exceedance_probability(strike_temp_c=24.0, ensemble_members=ensemble, station_id='KORD')
    assert res['method'] == 'EVT_GENERALIZED_PARETO'
    assert 0.0 < res['probability'] < 0.2
