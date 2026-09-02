from app.domain.dynamic_pipeline import DynamicUnderwritingEngine

def test_dynamic_underwriting_pipeline_trigger():
    engine = DynamicUnderwritingEngine()
    packet = engine.process_event_and_evaluate("KORD", 25.0, "2026-09-02T18:00:00Z", "KXCHICAGO-26SEP02", 0.42, 0.46)
    assert packet["estimated_probability"] == 0.75
    assert packet["edge"] == 0.29
    assert packet["recommended_action"] == "BUY_YES"
