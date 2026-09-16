from app.domain.ai_copilot import AICopilotEngine
from app.domain.context_harvester import ContextHarvester
from app.domain.ai_clients.mock_adapter import MockLLMClient

def test_context_harvester_defaults():
    h = ContextHarvester()
    ctx = h.harvest()
    assert ctx["governance"]["risk_ceiling_pct"] == 5.0
    assert ctx["governance"]["sizing_rule"] == "Quarter-Kelly (0.25 f*)"
    assert ctx["financial_state"]["total_balance_usd"] == 5000.0
    assert ctx["financial_state"]["reserved_margin_usd"] == 750.0
    assert "POLY-239496" in ctx["active_inventory"]["open_contracts"]

def test_copilot_engine_with_mock_client():
    mock_client = MockLLMClient()
    engine = AICopilotEngine(llm_client=mock_client)
    res = engine.process_query("Research opportunity in freeze weather contracts")
    assert res["unilateral_execution"] is False
    assert len(res["action_cards"]) == 1
    assert res["action_cards"][0]["action_type"] == "ORC_INSPECT"

def test_copilot_engine_kill_switch():
    mock_client = MockLLMClient()
    engine = AICopilotEngine(llm_client=mock_client)
    res = engine.process_query("Emergency stop the trading daemon")
    assert len(res["action_cards"]) == 1
    assert res["action_cards"][0]["action_type"] == "EMERGENCY_STOP"
    assert res["action_cards"][0]["destructive"] is True
