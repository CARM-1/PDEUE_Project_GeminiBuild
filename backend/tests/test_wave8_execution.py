from app.domain.execution_envelope import ExecutionEnvelope

def test_paper_execution_flow():
    envelope = ExecutionEnvelope(mode="PAPER")
    res = envelope.submit_order("CT-ECON-01", "BUY", 0.65, 100, "PKT-100")
    assert res["status"] == "SUCCESS"
    assert res["order"]["status"] == "FILLED"

def test_kill_switch_protection():
    envelope = ExecutionEnvelope(mode="PAPER")
    envelope.trigger_kill_switch("Risk threshold breached")
    res = envelope.submit_order("CT-ECON-01", "BUY", 0.65, 100, "PKT-100")
    assert res["status"] == "BLOCKED"
    assert res["reason"] == "KILL_SWITCH_ACTIVE"

def test_live_execution_gating():
    envelope = ExecutionEnvelope(mode="LIVE")
    res = envelope.submit_order("CT-ECON-01", "BUY", 0.65, 100, "PKT-100")
    assert res["status"] == "BLOCKED"
    assert res["reason"] == "LIVE_EXECUTION_UNAUTHORIZED"
