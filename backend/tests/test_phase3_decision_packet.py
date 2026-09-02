from app.domain.decision_packet import DecisionPacketBuilder

def test_decision_packet_builder_positive_edge():
    builder = DecisionPacketBuilder()
    packet = builder.build_decision_packet("EVT_KORD_01", raw_prob=0.80, yes_ask=0.50, total_capital=10000.0)
    assert packet["operating_mode"] == "NORMAL"
    assert packet["capital_bid"]["recommended_stake"] > 0
    assert len(packet["blocked_reasons"]) == 0

def test_decision_packet_builder_no_edge():
    builder = DecisionPacketBuilder()
    packet = builder.build_decision_packet("EVT_KORD_01", raw_prob=0.30, yes_ask=0.50, total_capital=10000.0)
    assert packet["operating_mode"] == "BLOCKED"
    assert packet["capital_bid"]["recommended_stake"] == 0.0
    assert "NO_STATISTICAL_EDGE" in packet["blocked_reasons"]
