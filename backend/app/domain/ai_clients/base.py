"""BaseLLMClient interface and constitutionally bounded LLMResponse model (Milestone F1)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .guardrails import (
    VALID_AUTH_TIERS,
    inspect_user_input,
    sanitize_action_cards,
    sanitize_output_text,
)


@dataclass
class LLMResponse:
    content: str
    action_cards: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    provider: str = "mock"
    model: str = "mock-engine"
    raw_payload: Optional[Dict[str, Any]] = None
    unilateral_execution: bool = False
    auth_tier: str = "AUTH-01"
    guard_triggered: bool = False
    guard_category: Optional[str] = None
    guard_reason: Optional[str] = None
    audit_event_id: Optional[str] = None
    fallback_used: bool = False
    requested_provider: Optional[str] = None
    impact_card: Optional[Dict[str, Any]] = None
    citations: List[str] = field(default_factory=list)
    web_citations: List[Dict[str, str]] = field(default_factory=list)
    grounding_used: bool = False
    structured_data: Optional[Dict[str, Any]] = None
    answered_locally: bool = False
    media_refs: List[Dict[str, Any]] = field(default_factory=list)
    playbook_steps: List[str] = field(default_factory=list)
    manual_citations: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.unilateral_execution is not False:
            raise ValueError(
                "Constitutional violation (AUTH-01–AUTH-04): unilateral_execution MUST be False."
            )
        tier = str(self.auth_tier or "AUTH-01").upper().strip()
        self.auth_tier = tier if tier in VALID_AUTH_TIERS else "AUTH-01"
        normalized_cards: List[Dict[str, Any]] = []
        for card in self.action_cards or []:
            if isinstance(card, dict):
                copy_card = dict(card)
                copy_card["unilateral_execution"] = False
                copy_card["executed"] = False
                copy_card.setdefault("requires_human_confirmation", True)
                card_tier = str(copy_card.get("auth_tier") or self.auth_tier).upper().strip()
                copy_card["auth_tier"] = card_tier if card_tier in VALID_AUTH_TIERS else "AUTH-01"
                normalized_cards.append(copy_card)
        self.action_cards = normalized_cards


class BaseLLMClient(ABC):
    """Pluggable LLM adapter contract with mandatory non-unilateral safety envelope."""

    provider_name: str = "base"
    model_name: str = "base"
    timeout_seconds: float = 15.0
    max_output_tokens: int = 1024

    @property
    def is_configured(self) -> bool:
        """Whether this adapter can execute live provider requests without falling back."""
        return True

    @abstractmethod
    def generate_response(
        self,
        system_prompt: str,
        user_query: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """Generate a bounded response. Never executes state mutations directly."""
        raise NotImplementedError

    def research_public_web(
        self,
        user_query: str,
        *,
        system_prompt: str = (
            "You are a read-only public market educator for a family financial literacy academy. "
            "Explain general economic, weather, energy, treasury, FX, equity-index, or binary probability "
            "concepts in plain English with verifiable public-source citations. "
            "Never give financial advice, never propose live trades, and enforce unilateral_execution=False."
        ),
        context: Optional[Dict[str, Any]] = None,
        actor_role: str = "MEMBER",
        actor_id: str = "member_user",
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Invoke read-only grounded public market research through this adapter."""
        research_ctx = dict(context or {})
        research_ctx["web_grounding"] = True
        if max_tokens is not None:
            research_ctx["max_output_tokens"] = max(64, min(int(max_tokens), int(self.max_output_tokens)))
        return self.generate_safe_response(
            system_prompt=system_prompt,
            user_query=user_query,
            context=research_ctx,
            actor_role=actor_role,
            actor_id=actor_id,
        )

    def generate_safe_response(
        self,
        system_prompt: str,
        user_query: str,
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
        actor_role: str = "MEMBER",
        actor_id: str = "member_user",
        allowed_scma_id: Optional[str] = None,
        member_name: Optional[str] = None,
        assigned_household_id: Optional[str] = None,
        r12_unredacted: bool = False,
        forbidden_scma_ids: Optional[List[str]] = None,
    ) -> LLMResponse:
        """Run input prompt-injection guard, invoke adapter, and sanitize output."""
        verdict = inspect_user_input(
            user_query,
            actor_role=actor_role,
            actor_id=actor_id,
            allowed_scma_id=allowed_scma_id,
            member_name=member_name,
            assigned_household_id=assigned_household_id,
            r12_unredacted=r12_unredacted,
            forbidden_scma_ids=forbidden_scma_ids,
        )
        if verdict.blocked:
            return LLMResponse(
                content=verdict.refusal_message or "Request refused under PDEUE constitutional guardrails.",
                action_cards=[],
                provider=self.provider_name if self.is_configured else "mock",
                model=self.model_name if self.is_configured else "mock-v1",
                unilateral_execution=False,
                auth_tier="AUTH-01",
                guard_triggered=True,
                guard_category=verdict.category,
                guard_reason=verdict.reason,
                audit_event_id=verdict.audit_event_id,
                fallback_used=not self.is_configured,
                requested_provider=self.provider_name if not self.is_configured else None,
            )

        scoped_context = dict(context or {})
        scoped_context.setdefault("actor_role", actor_role)
        scoped_context.setdefault("actor_id", actor_id)
        if allowed_scma_id:
            scoped_context.setdefault("allowed_scma_id", allowed_scma_id)
        if assigned_household_id:
            scoped_context.setdefault("assigned_household_id", assigned_household_id)
        scoped_context.setdefault("r12_unredacted", bool(r12_unredacted))
        if forbidden_scma_ids:
            scoped_context.setdefault("forbidden_scma_ids", list(forbidden_scma_ids))

        raw_response = self.generate_response(
            system_prompt=system_prompt,
            user_query=verdict.sanitized_text,
            tools=tools,
            context=scoped_context,
        )
        safe_content = sanitize_output_text(
            raw_response.content,
            actor_role=actor_role,
            allowed_scma_id=allowed_scma_id,
            r12_unredacted=r12_unredacted,
            forbidden_scma_ids=forbidden_scma_ids,
        )
        safe_cards = sanitize_action_cards(raw_response.action_cards, actor_role=actor_role)

        return LLMResponse(
            content=safe_content,
            action_cards=safe_cards,
            tool_calls=raw_response.tool_calls if actor_role.upper() != "MEMBER" else [],
            provider=raw_response.provider,
            model=raw_response.model,
            raw_payload=raw_response.raw_payload,
            unilateral_execution=False,
            auth_tier=raw_response.auth_tier,
            guard_triggered=raw_response.guard_triggered,
            guard_category=raw_response.guard_category,
            guard_reason=raw_response.guard_reason,
            audit_event_id=raw_response.audit_event_id,
            fallback_used=raw_response.fallback_used,
            requested_provider=raw_response.requested_provider,
            impact_card=raw_response.impact_card,
            citations=list(raw_response.citations),
            web_citations=list(raw_response.web_citations),
            grounding_used=bool(raw_response.grounding_used),
            structured_data=raw_response.structured_data,
            answered_locally=bool(raw_response.answered_locally),
            media_refs=list(raw_response.media_refs),
            playbook_steps=list(raw_response.playbook_steps),
            manual_citations=list(raw_response.manual_citations),
        )
