from datetime import datetime, timezone
from app.domain.calibration import ProbabilityCalibrator
from app.domain.replay_engine import ReplayEngine
from app.domain.decision_packet import DecisionPacketBuilder

def test_calibration():
    calibrator = ProbabilityCalibrator()
    assert calibrator.calibrate(0.50) == 0.50

def test_replay_engine():
    engine = ReplayEngine()
    cutoffs = [datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc), datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)]
    evidence = [{"published_at": "2026-09-01T11:00:00Z", "payload": {"temperature_c": 22.0}}]
    snapshot = {"market_id": "MKT-1", "contract_id": "CT-1", "yes_bid": 0.4, "yes_ask": 0.5, "timestamp": "2026-09-01T10:00:00Z"}
    replays = engine.run_replay(cutoffs, evidence, snapshot, strike_temp=20.0)
    assert len(replays) == 2
    assert replays[0]["result"]["admissible_count"] == 0
    assert replays[1]["result"]["admissible_count"] == 1

def test_decision_packet_builder():
    builder = DecisionPacketBuilder()
    packet = builder.build_packet("EV-100", "NORMAL", {"prob": 0.8}, {"admissible": True})
    assert packet["operating_mode"] == "NORMAL"
    assert packet["event_id"] == "EV-100"
