import pathlib

# 1. Ensure directories exist
base_dir = pathlib.Path("backend/app/domain/ai_clients")
base_dir.mkdir(parents=True, exist_ok=True)
test_dir = pathlib.Path("backend/tests")
test_dir.mkdir(parents=True, exist_ok=True)

# 2. Base Interfaces & Dataclasses
(base_dir / "base.py").write_text('''from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class LLMResponse:
    content: str
    action_cards: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    provider: str = "mock"
    model: str = "mock-engine"
    raw_payload: Optional[Dict[str, Any]] = None

class BaseLLMClient(ABC):
    @abstractmethod
    def generate_response(
        self,
        system_prompt: str,
        user_query: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        pass
''', encoding="utf-8")

# 3. Mock Adapter for CI/CD and Offline Testing
(base_dir / "mock_adapter.py").write_text('''import uuid
from typing import Any, Dict, List, Optional
from .base import BaseLLMClient, LLMResponse

class MockLLMClient(BaseLLMClient):
    def __init__(self, default_response: Optional[str] = None):
        self.default_response = default_response

    def generate_response(
        self,
        system_prompt: str,
        user_query: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        q = user_query.lower()
        action_cards: List[Dict[str, Any]] = []

        if any(w in q for w in ["kill", "emergency", "stop", "halt"]):
            content = "Emergency Kill Switch intent detected. Under AUTH-01, confirm using the Action Card below:"
            action_cards.append({
                "action_id": f"ACT-{uuid.uuid4().hex[:8]}",
                "action_type": "EMERGENCY_STOP",
                "title": "Trip Emergency Circuit Breaker",
                "description": "Immediate fail-closed halt of all scanning and execution loops.",
                "endpoint": "/api/v1/operator/emergency-stop",
                "method": "POST",
                "payload": {"actor_id": "Chief Administrator", "reason": "AI Kill Switch"},
                "destructive": True,
                "requires_dual_control": False
            })
        elif any(w in q for w in ["orc", "research", "hunch", "opportunity"]):
            content = "Opportunity Research Center (ORC): Evaluating hypothesis against Point-in-Time market data and active contract ladders."
            action_cards.append({
                "action_id": f"ACT-{uuid.uuid4().hex[:8]}",
                "action_type": "ORC_INSPECT",
                "title": "Open Opportunity Research Dossier",
                "description": "Launch ORC hypothesis evaluation drawer.",
                "endpoint": "/api/v1/operator/orc/dossier",
                "method": "GET",
                "payload": {"query": user_query},
                "destructive": False,
                "requires_dual_control": False
            })
        else:
            content = self.default_response or f"Mock LLM Response for: {user_query}"

        return LLMResponse(
            content=content,
            action_cards=action_cards,
            provider="mock",
            model="mock-v1"
        )
''', encoding="utf-8")

# 4. OpenAI Adapter with Dynamic Action Card Generation
(base_dir / "openai_adapter.py").write_text('''import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional
from .base import BaseLLMClient, LLMResponse

class OpenAILLMClient(BaseLLMClient):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self.endpoint = "https://api.openai.com/v1/chat/completions"

    def generate_response(
        self,
        system_prompt: str,
        user_query: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                content="OpenAI API key not configured. Set OPENAI_API_KEY environment variable.",
                provider="openai",
                model=self.model
            )

        msgs = [{"role": "system", "content": system_prompt}]
        if context:
            msgs.append({
                "role": "system",
                "content": f"Active PDEUE Operational Context:\n{json.dumps(context, indent=2)}"
            })
        msgs.append({"role": "user", "content": user_query})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            "temperature": 0.2
        }
        if tools:
            payload["tools"] = tools

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0].get("message", {})
                content = choice.get("content", "") or ""
                tool_calls = choice.get("tool_calls", [])
                action_cards = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except Exception:
                        args = {}
                    action_cards.append({
                        "action_id": f"ACT-{uuid.uuid4().hex[:8]}",
                        "action_type": fn_name or "ACTION",
                        "title": args.get("title", f"Execute {fn_name}"),
                        "description": args.get("description", "AI operation."),
                        "endpoint": args.get("endpoint", "/api/v1/operator/action"),
                        "method": args.get("method", "POST"),
                        "payload": args.get("payload", {}),
                        "destructive": args.get("destructive", False),
                        "requires_dual_control": args.get("requires_dual_control", False)
                    })
                return LLMResponse(
                    content=content,
                    action_cards=action_cards,
                    tool_calls=tool_calls,
                    provider="openai",
                    model=self.model,
                    raw_payload=data
                )
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            return LLMResponse(
                content=f"OpenAI API error ({e.code}): {err_body}",
                provider="openai",
                model=self.model
            )
        except Exception as e:
            return LLMResponse(
                content=f"Connection error to OpenAI: {str(e)}",
                provider="openai",
                model=self.model
            )
''', encoding="utf-8")

# 5. Gemini Adapter Staging
(base_dir / "gemini_adapter.py").write_text('''import os
from typing import Any, Dict, List, Optional
from .base import BaseLLMClient, LLMResponse

class GeminiLLMClient(BaseLLMClient):
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-pro"):
        self.api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self.model = model

    def generate_response(
        self,
        system_prompt: str,
        user_query: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                content="Gemini API key not configured. Set GEMINI_API_KEY.",
                provider="gemini",
                model=self.model
            )
        return LLMResponse(
            content="Gemini adapter staged and ready for activation.",
            provider="gemini",
            model=self.model
        )
''', encoding="utf-8")

# 6. Factory Dispatcher
(base_dir / "factory.py").write_text('''import os
from typing import Optional
from .base import BaseLLMClient
from .gemini_adapter import GeminiLLMClient
from .mock_adapter import MockLLMClient
from .openai_adapter import OpenAILLMClient

def get_llm_client(provider_override: Optional[str] = None) -> BaseLLMClient:
    provider = provider_override or os.getenv("AI_PROVIDER")
    if not provider:
        if os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif os.getenv("GEMINI_API_KEY"):
            provider = "gemini"
        else:
            provider = "mock"
    provider = provider.lower().strip()
    if provider == "openai":
        return OpenAILLMClient()
    elif provider == "gemini":
        return GeminiLLMClient()
    return MockLLMClient()
''', encoding="utf-8")

# 7. Domain Package Init
(base_dir / "__init__.py").write_text('''from .base import BaseLLMClient, LLMResponse
from .factory import get_llm_client
from .gemini_adapter import GeminiLLMClient
from .mock_adapter import MockLLMClient
from .openai_adapter import OpenAILLMClient

__all__ = [
    "BaseLLMClient",
    "LLMResponse",
    "MockLLMClient",
    "OpenAILLMClient",
    "GeminiLLMClient",
    "get_llm_client",
]
''', encoding="utf-8")

# 8. Test Suite
(test_dir / "test_ai_clients.py").write_text('''from app.domain.ai_clients import (
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
''', encoding="utf-8")

print("All AI client modules and test suites successfully written.")