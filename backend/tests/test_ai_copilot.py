from app.domain.ai_copilot import AICopilotEngine

def test_copilot_kill_switch_action_card():
    engine = AICopilotEngine()
    res = engine.process_query('trip the emergency kill switch')
    assert res['unilateral_execution'] is False
    assert len(res['action_cards']) == 1
    card = res['action_cards'][0]
    assert card['action_type'] == 'EMERGENCY_STOP'
    assert card['destructive'] is True
    assert card['endpoint'] == '/api/v1/operator/emergency-stop'

def test_copilot_contract_explanation():
    engine = AICopilotEngine()
    res = engine.process_query('explain contract KX-ORD-26 edge')
    assert 'KX-ORD-26' in res['response_text']
    assert len(res['action_cards']) == 1
    assert res['action_cards'][0]['action_type'] == 'INSPECT_CONTRACT'
    assert res['lineage_context']['model_prob'] == 0.27

def test_copilot_risk_telemetry():
    engine = AICopilotEngine()
    state = {'founder_scma': {'cash_balance_cents': 10000000}, 'cfcp_cents': 50000, 'faep_cents': 15000}
    res = engine.process_query('audit portfolio risk and waterfall', workspace_state=state)
    assert '87%' in res['response_text']
    assert res['action_cards'][0]['action_type'] == 'TELEMETRY_REFRESH'
