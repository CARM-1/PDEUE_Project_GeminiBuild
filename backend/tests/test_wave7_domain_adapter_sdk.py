import pytest
from app.domain.domain_adapter_sdk import BaseDomainAdapter, EconomicIndicatorAdapter

def test_economic_domain_adapter_conformance():
    adapter = EconomicIndicatorAdapter()
    assert isinstance(adapter, BaseDomainAdapter)

    raw_spec = {
        "event_id": "EVT-ECON-CPI-2026-08",
        "series_id": "CPIAUCSL",
        "threshold": 3.0,
        "target_period": "2026-08",
        "resolution_authority": "US_BLS"
    }
    event_def = adapter.map_event_definition(raw_spec)
    assert event_def["event_id"] == "EVT-ECON-CPI-2026-08"
    assert event_def["domain"] == "MACROECONOMIC"
    assert event_def["status"] == "REGISTERED"

    pit_evidence = [
        {"source": "CONSENSUS_A", "value": 3.15, "available_at": "2026-09-01T10:00:00Z"},
        {"source": "CONSENSUS_B", "value": 3.25, "available_at": "2026-09-02T12:00:00Z"},
        {"source": "CONSENSUS_C", "value": 3.20, "available_at": "2026-09-02T14:00:00Z"}
    ]
    features = adapter.extract_features(pit_evidence)
    features["threshold"] = event_def["threshold"]
    assert features["observations_count"] == 3
    assert features["latest_consensus"] == 3.20
    assert features["dispersion"] == 0.10

    artifact = adapter.underwrite(features)
    assert artifact["domain"] == "MACROECONOMIC"
    assert artifact["calibrated_probability"] > 0.50
    assert artifact["fair_value_cents"] > 50.0
    assert "sealed_at" in artifact

def test_economic_adapter_empty_evidence():
    adapter = EconomicIndicatorAdapter()
    features = adapter.extract_features([])
    assert features["observations_count"] == 0
    artifact = adapter.underwrite(features)
    assert 0.0 < artifact["calibrated_probability"] < 1.0
