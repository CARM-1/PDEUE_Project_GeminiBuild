from app.domain.data_ingestion import DataIngestionEngine

def test_noaa_ingestion_and_pit_filter():
    engine = DataIngestionEngine()
    rec1 = engine.ingest_noaa_observation("KORD", 22.5, "2026-09-02T12:00:00Z")
    rec2 = engine.ingest_noaa_observation("KORD", 24.0, "2026-09-02T16:00:00Z")
    
    assert rec1["validated"] is True
    
    # Point-in-time cutoff at 14:00:00Z should only return rec1
    pit_records = engine.filter_point_in_time("2026-09-02T14:00:00Z")
    assert len(pit_records) == 1
    assert pit_records[0]["observation"]["temperature_c"] == 22.5
