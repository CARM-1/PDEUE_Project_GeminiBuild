from app.adapters.weather import NOAAAdapter

def test_noaa_adapter_parsing():
    adapter = NOAAAdapter()
    res = adapter.parse_observation({"id": "OBS-101", "timestamp": "2026-09-01T10:00:00Z", "temp": 21.5})
    assert res["source"] == "NOAA_NWS"
    assert res["payload"]["temperature_c"] == 21.5
