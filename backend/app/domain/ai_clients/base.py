from abc import ABC, abstractmethod
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
