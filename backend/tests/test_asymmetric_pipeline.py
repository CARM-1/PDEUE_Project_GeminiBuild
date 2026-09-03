from datetime import datetime, timezone
from app.adapters.ensemble_weather_adapter import EnsembleWeatherAdapter
from app.domain.advanced_underwriting_pipeline import AdvancedUnderwritingPipeline

def test_ensemble_adapter_parsing():
    adapter = EnsembleWeatherAdapter()
    raw = {
        'evidence_id': 'EV-GEFS-01',
        'model_source': 'NOAA_GEFS',
        'station_id': 'KORD',
        'published_at': '2026-09-03T06:00:00Z',
        'member_forecasts_c': [22.0, 22.5, 23.0, 22.8, 23.5]
    }
    parsed = adapter.parse_ensemble_payload(raw)
    assert parsed['source'] == 'NOAA_GEFS'
    assert parsed['station_id'] == 'KORD'
    assert parsed['payload']['ensemble_size'] == 5

def test_advanced_underwriting_pipeline_e2e():
    pipeline = AdvancedUnderwritingPipeline()
    cutoff = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    
    evidence = [
        {
            'evidence_id': 'EV-ENS-01',
            'published_at': '2026-09-03T08:00:00Z',
            'payload': {'member_temperatures_c': [24.0, 24.5, 25.0, 25.2, 24.8]}
        },
        {
            'evidence_id': 'EV-ENS-LEAK',
            'published_at': '2026-09-03T13:30:00Z',
            'payload': {'member_temperatures_c': [30.0, 31.0]}
        }
    ]
    
    snapshot = {'market_id': 'MKT-WX-01', 'contract_id': 'CT-KORD-26', 'yes_bid': 0.35, 'yes_ask': 0.40, 'timestamp': '2026-09-03T12:00:00Z'}
    
    result = pipeline.run_underwriting(
        cutoff=cutoff,
        evidence_items=evidence,
        market_snapshot=snapshot,
        strike_temp_c=25.0,
        station_id='KORD'
    )
    
    assert result['admissible_count'] == 1
    assert result['station_id'] == 'KORD'
    assert result['distribution']['mu'] > 24.5
    assert result['model_probability'] > 0.0
    assert result['edge_metrics']['raw_edge'] is not None
