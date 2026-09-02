from datetime import datetime, timezone
from app.domain.underwriting_pipeline import UnderwritingPipeline

def test_underwriting_pipeline():
    pipeline = UnderwritingPipeline()
    cutoff = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    evidence = [
        {"published_at": "2026-09-01T11:00:00Z", "payload": {"temperature_c": 24.0}},
        {"published_at": "2026-09-01T13:00:00Z", "payload": {"temperature_c": 26.0}}
    ]
    snapshot = {"market_id": "MKT-01", "contract_id": "CT-01", "yes_bid": 0.40, "yes_ask": 0.44, "timestamp": "2026-09-01T12:00:00Z"}
    result = pipeline.run_underwriting(cutoff, evidence, snapshot, strike_temp=20.0)
    assert result["admissible_count"] == 1
    assert result["model_probability"] == 1.0
    assert result["edge_metrics"]["raw_edge"] == 0.58
