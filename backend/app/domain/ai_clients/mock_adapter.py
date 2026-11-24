"""Deterministic $0 MockLLMClient adapter (default in paper/CI mode)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid

from .base import BaseLLMClient, LLMResponse
from .guardrails import inspect_user_input, sanitize_action_cards, sanitize_output_text


class MockLLMClient(BaseLLMClient):
    """Zero-cost deterministic LLM adapter for paper mode, offline local dev, and CI."""

    provider_name = "mock"
    model_name = "mock-v1"

    def __init__(self, default_response: Optional[str] = None):
        self.default_response = default_response

    @property
    def is_configured(self) -> bool:
        return True

    def generate_response(
        self,
        system_prompt: str,
        user_query: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        ctx = dict(context or {})
        actor_role = str(ctx.get("actor_role") or "OPERATOR").upper().strip()
        allowed_scma_id = ctx.get("allowed_scma_id") or ctx.get("scma_id")
        member_name = ctx.get("member_name") or ctx.get("name")
        actor_id = str(ctx.get("actor_id") or allowed_scma_id or actor_role.lower())

        # Enforce prompt-injection / exfiltration guard even on direct calls.
        verdict = inspect_user_input(
            user_query,
            actor_role=actor_role,
            actor_id=actor_id,
            allowed_scma_id=allowed_scma_id,
            member_name=member_name,
        )
        if verdict.blocked:
            return LLMResponse(
                content=verdict.refusal_message or "Request refused under PDEUE guardrails.",
                action_cards=[],
                provider=self.provider_name,
                model=self.model_name,
                unilateral_execution=False,
                auth_tier="AUTH-01",
                guard_triggered=True,
                guard_category=verdict.category,
                guard_reason=verdict.reason,
                audit_event_id=verdict.audit_event_id,
            )

        # Grounded Class M Member Tutor draft passthrough (deterministic, isolated).
        if actor_role == "MEMBER" and isinstance(ctx.get("tutor_draft"), dict):
            draft = ctx["tutor_draft"]
            content = sanitize_output_text(
                str(draft.get("content") or self.default_response or ""),
                actor_role="MEMBER",
                allowed_scma_id=allowed_scma_id,
            )
            cards = sanitize_action_cards(list(draft.get("action_cards") or []), actor_role="MEMBER")
            return LLMResponse(
                content=content,
                action_cards=cards,
                provider=self.provider_name,
                model=self.model_name,
                unilateral_execution=False,
                auth_tier=str(draft.get("auth_tier") or "AUTH-01"),
                impact_card=draft.get("impact_card"),
                citations=list(draft.get("citations") or []),
            )

        q = verdict.sanitized_text.lower()
        action_cards: List[Dict[str, Any]] = []
        auth_tier = "AUTH-01"

        if actor_role != "MEMBER" and any(w in q for w in ["kill", "emergency", "stop", "halt"]):
            auth_tier = "AUTH-04"
            content = "Emergency Kill Switch intent detected. Under AUTH-01, confirm using the Action Card below:"
            action_cards.append({
                "action_id": f"ACT-{uuid.uuid4().hex[:8]}",
                "action_type": "EMERGENCY_STOP",
                "auth_tier": "AUTH-04",
                "title": "Trip Emergency Circuit Breaker",
                "description": "Immediate fail-closed halt of all scanning and execution loops.",
                "endpoint": "/api/v1/operator/emergency-stop",
                "method": "POST",
                "payload": {"actor_id": "Chief Administrator", "reason": "AI Kill Switch"},
                "destructive": True,
                "requires_dual_control": False,
                "requires_human_confirmation": True,
                "unilateral_execution": False,
                "executed": False,
            })
        elif actor_role != "MEMBER" and any(w in q for w in ["orc", "research", "hunch", "opportunity"]):
            auth_tier = "AUTH-01"
            content = "Opportunity Research Center (ORC): Evaluating hypothesis against Point-in-Time market data and active contract ladders."
            action_cards.append({
                "action_id": f"ACT-{uuid.uuid4().hex[:8]}",
                "action_type": "ORC_INSPECT",
                "auth_tier": "AUTH-01",
                "title": "Open Opportunity Research Dossier",
                "description": "Launch ORC hypothesis evaluation drawer.",
                "endpoint": "/api/v1/operator/orc/dossier",
                "method": "GET",
                "payload": {"query": verdict.sanitized_text},
                "destructive": False,
                "requires_dual_control": False,
                "requires_human_confirmation": True,
                "unilateral_execution": False,
                "executed": False,
            })
        else:
            content = self.default_response or f"Mock LLM Response for: {verdict.sanitized_text}"

        return LLMResponse(
            content=sanitize_output_text(content, actor_role=actor_role, allowed_scma_id=allowed_scma_id),
            action_cards=sanitize_action_cards(action_cards, actor_role=actor_role),
            provider=self.provider_name,
            model=self.model_name,
            unilateral_execution=False,
            auth_tier=auth_tier,
        )
