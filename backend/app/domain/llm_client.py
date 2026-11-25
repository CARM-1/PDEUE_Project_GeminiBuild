"""Modular LLM Client Adapter (Batch 2B — Part 1).

Provides a single, clean Adapter Pattern entrypoint built on top of the
constitutionally bounded ``BaseLLMClient`` hierarchy:

- ``MockLLMClient``: Deterministic offline provider ($0 CI default when
  ``AI_PROVIDER`` is unset or ``mock``, or when hosted API keys are absent).
  Returns structured plain-English teaching answers and deterministic mock web
  citations for Lane 2 public market research.
- ``GeminiLLMClient``: Activates when ``AI_PROVIDER=gemini`` and
  ``GEMINI_API_KEY`` is set; supports Google Search grounding for Lane 2.
- ``OpenAILLMClient``: Activates when ``AI_PROVIDER=openai`` and
  ``OPENAI_API_KEY`` is set; swappable without modifying routers or templates.

Constitutional & Hygiene Invariants:
- ``unilateral_execution = False`` enforced across every adapter & response.
- Per-request timeout & output token cap enforced on hosted adapters.
- Automatic fail-closed fallback to ``MockLLMClient`` on missing keys or errors.
- Zero imports of live trading ledgers, risk envelopes, or banking credentials.
"""
from __future__ import annotations

import os
from typing import Optional

from app.domain.ai_clients.base import BaseLLMClient, LLMResponse
from app.domain.ai_clients.gemini_adapter import GeminiLLMClient
from app.domain.ai_clients.mock_adapter import MockLLMClient
from app.domain.ai_clients.openai_adapter import OpenAILLMClient

DEFAULT_AI_PROVIDER = "mock"


def get_llm_client(
    provider_override: Optional[str] = None,
    *,
    fail_closed_to_mock: bool = True,
    timeout_seconds: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
) -> BaseLLMClient:
    """Resolve an active ``BaseLLMClient`` adapter from ``AI_PROVIDER``.

    Default behavior (zero-cost deterministic CI):
    - When ``AI_PROVIDER`` is unset or ``mock``, returns ``MockLLMClient``.
    - When ``AI_PROVIDER=gemini`` and ``GEMINI_API_KEY`` is set, returns ``GeminiLLMClient``.
    - When ``AI_PROVIDER=openai`` and ``OPENAI_API_KEY`` is set, returns ``OpenAILLMClient``.
    - When ``fail_closed_to_mock=True`` (default) and a requested provider's API key
      is missing, fails closed directly to ``MockLLMClient`` with zero network calls.
    """
    raw_provider = (
        provider_override
        if provider_override is not None
        else os.getenv("AI_PROVIDER", DEFAULT_AI_PROVIDER)
    )
    provider = (raw_provider or DEFAULT_AI_PROVIDER).strip().lower()

    if provider == "gemini":
        client: BaseLLMClient = GeminiLLMClient(
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )
        if fail_closed_to_mock and not client.is_configured:
            return MockLLMClient(
                timeout_seconds=timeout_seconds or 15.0,
                max_output_tokens=max_output_tokens or 1024,
            )
        return client

    if provider == "openai":
        client = OpenAILLMClient(
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )
        if fail_closed_to_mock and not client.is_configured:
            return MockLLMClient(
                timeout_seconds=timeout_seconds or 15.0,
                max_output_tokens=max_output_tokens or 1024,
            )
        return client

    return MockLLMClient(
        timeout_seconds=timeout_seconds or 15.0,
        max_output_tokens=max_output_tokens or 1024,
    )


__all__ = [
    "BaseLLMClient",
    "DEFAULT_AI_PROVIDER",
    "GeminiLLMClient",
    "LLMResponse",
    "MockLLMClient",
    "OpenAILLMClient",
    "get_llm_client",
]
