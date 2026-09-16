import uuid
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
