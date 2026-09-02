from app.domain.operator import OperatorControlEngine

def test_operator_paper_session_and_audit():
    engine = OperatorControlEngine()
    session = engine.start_paper_session("tenant_alpha", 50000.0)
    assert session["status"] == "ACTIVE"
    assert session["current_balance"] == 50000.0
    
    assert len(engine.audit_log) == 1
    assert engine.audit_log[0]["action"] == "SESSION_STARTED"
