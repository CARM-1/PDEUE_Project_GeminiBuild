"""OpenAILLMClient adapter with fail-closed fallback to MockLLMClient (Milestone F1)."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request
import uuid

from .base import BaseLLMClient, LLMResponse
from .guardrails import inspect_user_input, sanitize_action_cards, sanitize_output_text
from .mock_adapter import MockLLMClient


class OpenAILLMClient(BaseLLMClient):
    """OpenAI Chat Completions REST adapter (zero hardcoded secrets; fails closed to MockLLMClient)."""

    provider_name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        fallback_client: Optional[BaseLLMClient] = None,
        timeout_seconds: float = 20.0,
    ):
        self.api_key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
        self.model = (model or os.getenv("OPENAI_MODEL", "gpt-4o")).strip()
        self.model_name = self.model
        self.timeout_seconds = float(timeout_seconds)
        self._fallback = fallback_client or MockLLMClient()
        self.endpoint = "https://api.openai.com/v1/chat/completions"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _fail_closed_fallback(
        self,
        *,
        system_prompt: str,
        user_query: str,
        tools: Optional[List[Dict[str, Any]]],
        context: Optional[Dict[str, Any]],
        notice: str,
    ) -> LLMResponse:
        mock_resp = self._fallback.generate_response(
            system_prompt=system_prompt,
            user_query=user_query,
            tools=tools,
            context=context,
        )
        combined = f"{notice}\n\n{mock_resp.content}".strip() if mock_resp.content else notice
        return LLMResponse(
            content=combined,
            action_cards=mock_resp.action_cards,
            provider="mock",
            model=mock_resp.model,
            unilateral_execution=False,
            auth_tier=mock_resp.auth_tier,
            guard_triggered=mock_resp.guard_triggered,
            guard_category=mock_resp.guard_category,
            guard_reason=mock_resp.guard_reason,
            audit_event_id=mock_resp.audit_event_id,
            fallback_used=True,
            requested_provider=self.provider_name,
            impact_card=mock_resp.impact_card,
            citations=list(mock_resp.citations),
            structured_data=mock_resp.structured_data,
        )

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
        assigned_household_id = ctx.get("assigned_household_id")
        r12_unredacted = bool(ctx.get("r12_unredacted", False))
        forbidden_scma_ids = ctx.get("forbidden_scma_ids")

        # Always guard BEFORE checking credentials or issuing network requests.
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
                content=verdict.refusal_message or "Request refused under PDEUE guardrails.",
                action_cards=[],
                provider="mock" if not self.is_configured else self.provider_name,
                model="mock-v1" if not self.is_configured else self.model,
                unilateral_execution=False,
                auth_tier="AUTH-01",
                guard_triggered=True,
                guard_category=verdict.category,
                guard_reason=verdict.reason,
                audit_event_id=verdict.audit_event_id,
                fallback_used=not self.is_configured,
                requested_provider=self.provider_name if not self.is_configured else None,
            )

        if not self.is_configured:
            return self._fail_closed_fallback(
                system_prompt=system_prompt,
                user_query=verdict.sanitized_text,
                tools=tools,
                context=ctx,
                notice="OpenAI API key not configured. Set OPENAI_API_KEY environment variable (fail-closed fallback to MockLLMClient).",
            )

        safe_ctx = {k: v for k, v in ctx.items() if k not in {"tutor_draft", "copilot_draft"}}
        msgs = [{"role": "system", "content": system_prompt}]
        if safe_ctx:
            msgs.append({
                "role": "system",
                "content": f"Active PDEUE Scoped Context:\n{json.dumps(safe_ctx, indent=2, default=str)}",
            })
        msgs.append({"role": "user", "content": verdict.sanitized_text})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            "temperature": 0.2,
        }
        if tools and actor_role != "MEMBER":
            payload["tools"] = tools

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0].get("message", {})
                content = choice.get("content", "") or ""
                tool_calls = choice.get("tool_calls", [])
                action_cards: List[Dict[str, Any]] = []
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
                        "auth_tier": args.get("auth_tier", "AUTH-02"),
                        "title": args.get("title", f"Review {fn_name}"),
                        "description": args.get("description", "Staged AI proposal requiring human confirmation."),
                        "endpoint": args.get("endpoint", "/api/v1/operator/action"),
                        "method": args.get("method", "POST"),
                        "payload": args.get("payload", {}),
                        "destructive": bool(args.get("destructive", False)),
                        "requires_dual_control": bool(args.get("requires_dual_control", False)),
                        "requires_human_confirmation": True,
                        "unilateral_execution": False,
                        "executed": False,
                    })
                draft = (
                    ctx.get("copilot_draft")
                    if isinstance(ctx.get("copilot_draft"), dict)
                    else (ctx.get("tutor_draft") if isinstance(ctx.get("tutor_draft"), dict) else {})
                )
                if draft.get("action_cards"):
                    action_cards.extend(list(draft["action_cards"]))
                return LLMResponse(
                    content=sanitize_output_text(
                        content,
                        actor_role=actor_role,
                        allowed_scma_id=allowed_scma_id,
                        r12_unredacted=r12_unredacted,
                        forbidden_scma_ids=forbidden_scma_ids,
                    ),
                    action_cards=sanitize_action_cards(action_cards, actor_role=actor_role),
                    tool_calls=tool_calls if actor_role != "MEMBER" else [],
                    provider=self.provider_name,
                    model=self.model,
                    raw_payload=data,
                    unilateral_execution=False,
                    auth_tier=str(draft.get("auth_tier") or "AUTH-01"),
                    impact_card=draft.get("impact_card"),
                    citations=list(draft.get("citations") or []),
                    structured_data=draft.get("structured_data"),
                )
        except (urllib.error.HTTPError, urllib.error.URLError, Exception) as exc:
            return self._fail_closed_fallback(
                system_prompt=system_prompt,
                user_query=verdict.sanitized_text,
                tools=tools,
                context=ctx,
                notice=f"OpenAI adapter unavailable ({type(exc).__name__}); failed closed to MockLLMClient.",
            )
