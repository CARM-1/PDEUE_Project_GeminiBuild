from app.domain.ai_clients import (
    GeminiLLMClient,
    LLMResponse,
    MockLLMClient,
    OpenAILLMClient,
    get_llm_client,
)

def test_mock_client_defaults():
    c = MockLLMClient()
    r = c.generate_response("System", "What is the risk dial?")
    assert isinstance(r, LLMResponse)
    assert r.provider == "mock"
    assert "mock-v1" in r.model
    assert len(r.action_cards) == 0

def test_mock_client_kill_switch():
    c = MockLLMClient()
    r = c.generate_response("System", "Please emergency stop now")
    assert len(r.action_cards) == 1
    assert r.action_cards[0]["action_type"] == "EMERGENCY_STOP"
    assert r.action_cards[0]["destructive"] is True

def test_mock_client_orc_intent():
    c = MockLLMClient()
    r = c.generate_response("System", "Research opportunity in freeze weather derivatives")
    assert len(r.action_cards) == 1
    assert r.action_cards[0]["action_type"] == "ORC_INSPECT"
    assert r.action_cards[0]["endpoint"] == "/api/v1/operator/orc/dossier"

def test_factory_selection(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    assert isinstance(get_llm_client(), MockLLMClient)
    monkeypatch.setenv("AI_PROVIDER", "openai")
    assert isinstance(get_llm_client(), OpenAILLMClient)
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    assert isinstance(get_llm_client(), GeminiLLMClient)

def test_openai_missing_key():
    c = OpenAILLMClient(api_key="")
    r = c.generate_response("sys", "query")
    assert "OpenAI API key not configured" in r.content
