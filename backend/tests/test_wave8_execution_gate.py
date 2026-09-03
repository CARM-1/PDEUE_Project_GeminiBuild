from app.domain.execution_gate import ExecutionPolicyGate, PreTradeValidator

def test_execution_policy_gate_paper_mode():
    gate = ExecutionPolicyGate(mode="PAPER")
    intent = {"decision_packet_id": "PKT-001", "total_cost_cents": 50000}
    res = gate.authorize_execution_intent(intent, account_reservation={"reserved": True, "reserved_cents": 60000})
    assert res["authorized"] is True
    assert res["mode"] == "PAPER"

def test_execution_policy_gate_research_denial():
    gate = ExecutionPolicyGate(mode="RESEARCH")
    intent = {"decision_packet_id": "PKT-002", "total_cost_cents": 10000}
    res = gate.authorize_execution_intent(intent, account_reservation={"reserved": True, "reserved_cents": 20000})
    assert res["authorized"] is False
    assert res["reason"] == "RESEARCH_MODE_NO_EXECUTION"

def test_execution_policy_gate_unlocked_production():
    gate = ExecutionPolicyGate(mode="PRODUCTION")
    intent = {"decision_packet_id": "PKT-003", "total_cost_cents": 10000}
    res = gate.authorize_execution_intent(intent, account_reservation={"reserved": True, "reserved_cents": 20000})
    assert res["authorized"] is False
    assert res["reason"] == "PRODUCTION_GATED_LOCKED"
    gate.unlock_production("AUTH-PROD-GATED-SECRET")
    res_unlocked = gate.authorize_execution_intent(intent, account_reservation={"reserved": True, "reserved_cents": 20000})
    assert res_unlocked["authorized"] is True

def test_pre_trade_validator_boundaries():
    validator = PreTradeValidator()
    bad_price = {"idempotency_key": "k-1", "side": "BUY", "price": 1.05, "quantity": 10}
    assert validator.validate_order(bad_price)["valid"] is False
    valid_order = {"idempotency_key": "k-2", "side": "BUY", "price": 0.65, "quantity": 10}
    res = validator.validate_order(valid_order)
    assert res["valid"] is True
    dup_order = {"idempotency_key": "k-2", "side": "BUY", "price": 0.65, "quantity": 10}
    assert validator.validate_order(dup_order)["reason"] == "DUPLICATE_IDEMPOTENCY_KEY"
