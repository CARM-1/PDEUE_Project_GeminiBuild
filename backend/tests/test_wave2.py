from app.adapters.weather import NOAAAdapter
from app.domain.weather_engine import WeatherProbabilityEngine
from app.domain.contract_mapper import ContractMapper

def test_noaa_adapter_parsing():
    adapter = NOAAAdapter()
    res = adapter.parse_observation({"id": "OBS-101", "timestamp": "2026-09-01T10:00:00Z", "temp": 21.5})
    assert res["source"] == "NOAA_NWS"
    assert res["payload"]["temperature_c"] == 21.5

def test_weather_probability_engine():
    engine = WeatherProbabilityEngine()
    evidence = [
        {"payload": {"temperature_c": 22.0}},
        {"payload": {"temperature_c": 25.0}},
        {"payload": {"temperature_c": 19.0}}
    ]
    prob = engine.compute_probability(evidence, strike_temp_c=20.0)
    assert prob == 0.6667

def test_contract_mapper_evaluation():
    mapper = ContractMapper()
    contract = {"contract_id": "CT-W01", "metric": "temperature_c", "strike_value": 20.0}
    obs = {"payload": {"temperature_c": 21.5}}
    assert mapper.evaluate_resolution(contract, obs) is True
