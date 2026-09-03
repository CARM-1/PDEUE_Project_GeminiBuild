from app.domain.circuit_breaker import CircuitBreakerEngine

def test_circuit_breaker_normal_and_trip():
    cb = CircuitBreakerEngine()
    assert cb.validate_execution_allowed() is True
    
    trip_record = cb.trip("Excessive market volatility detected", actor_id="risk_monitor_01")
    assert cb.is_tripped is True
    assert cb.validate_execution_allowed() is False
    assert trip_record["action"] == "CIRCUIT_BREAKER_TRIPPED"
    assert len(cb.trip_history) == 1

def test_circuit_breaker_reset_recovery():
    cb = CircuitBreakerEngine()
    cb.trip("Exchange API desync", actor_id="system_watchdog")
    assert cb.validate_execution_allowed() is False
    
    reset_record = cb.reset(actor_id="admin_trader", justification="Exchange connection restored and verified")
    assert cb.is_tripped is False
    assert cb.validate_execution_allowed() is True
    assert reset_record["action"] == "CIRCUIT_BREAKER_RESET"
    assert len(cb.trip_history) == 2
