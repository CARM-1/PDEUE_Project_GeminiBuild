from datetime import datetime, timezone
from app.domain.pit_selector import PITSelector

def test_pit_selector_filters_future_data():
    cutoff = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    selector = PITSelector(cutoff_time=cutoff)

    evidence = [
        {"evidence_id": "EV-001", "published_at": "2026-09-01T11:59:00Z", "payload": {"temp": 72}},
        {"evidence_id": "EV-002", "published_at": "2026-09-01T12:05:00Z", "payload": {"temp": 75}}
    ]

    filtered = selector.filter_admissible_evidence(evidence)
    assert len(filtered) == 1
    assert filtered[0]["evidence_id"] == "EV-001"
