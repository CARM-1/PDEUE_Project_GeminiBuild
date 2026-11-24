"""GeminiLLMClient adapter with fail-closed fallback to MockLLMClient (Milestone F1)."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

from .base import BaseLLMClient, LLMResponse
from .guardrails import inspect_user_input, sanitize_action_cards, sanitize_output_text
from .mock_adapter import MockLLMClient


class GeminiLLMClient(BaseLLMClient):
    """Google Gemini REST adapter (zero hardcoded secrets; fails closed to MockLLMClient)."""

    provider_name = "gemini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        fallback_client: Optional[BaseLLMClient] = None,
        timeout_seconds: float = 20.0,
    ):
        self.api_key = (api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        self.model = (model or os.getenv("GEMINI_MODEL", "gemini-2.5-pro")).strip()
        self.model_name = self.model
        self.timeout_seconds = float(timeout_seconds)
        self._fallback = fallback_client or MockLLMClient()
        self.endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )

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

        # Always guard BEFORE checking credentials or making outbound calls.
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
                notice="Gemini API key not configured (fail-closed fallback to MockLLMClient).",
            )

        safe_ctx = {k: v for k, v in ctx.items() if k not in {"tutor_draft", "copilot_draft"}}
        prompt_parts = [
            f"System Policy (AUTH-01–AUTH-04, unilateral_execution=False):\n{system_prompt}",
        ]
        if safe_ctx:
            prompt_parts.append(f"Scoped Context:\n{json.dumps(safe_ctx, default=str)}")
        prompt_parts.append(f"User Query:\n{verdict.sanitized_text}")

        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": "\n\n".join(prompt_parts)}]}],
            "generationConfig": {"temperature": 0.2},
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates") or []
                parts = (candidates[0].get("content", {}).get("parts", []) if candidates else [])
                text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
                draft = (
                    ctx.get("copilot_draft")
                    if isinstance(ctx.get("copilot_draft"), dict)
                    else (ctx.get("tutor_draft") if isinstance(ctx.get("tutor_draft"), dict) else {})
                )
                cards = sanitize_action_cards(list(draft.get("action_cards") or []), actor_role=actor_role)
                return LLMResponse(
                    content=sanitize_output_text(
                        text,
                        actor_role=actor_role,
                        allowed_scma_id=allowed_scma_id,
                        r12_unredacted=r12_unredacted,
                        forbidden_scma_ids=forbidden_scma_ids,
                    ),
                    action_cards=cards,
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
                notice=f"Gemini adapter unavailable ({type(exc).__name__}); failed closed to MockLLMClient.",
            )
