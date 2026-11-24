"""Environment-driven factory for PDEUE BaseLLMClient adapters (Milestone F1)."""
from __future__ import annotations

import os
from typing import Optional

from .base import BaseLLMClient
from .gemini_adapter import GeminiLLMClient
from .mock_adapter import MockLLMClient
from .openai_adapter import OpenAILLMClient


def get_llm_client(
    provider_override: Optional[str] = None,
    *,
    fail_closed_to_mock: bool = False,
) -> BaseLLMClient:
    """Resolve a ``BaseLLMClient`` adapter from environment configuration.

    Defaults to ``MockLLMClient`` ($0 deterministic) whenever no API key is configured.
    When ``fail_closed_to_mock=True``, any requested hosted adapter lacking credentials
    fails closed directly to ``MockLLMClient`` at factory resolution time.
    """
    provider = provider_override or os.getenv("AI_PROVIDER") or os.getenv("PDEUE_LLM_PROVIDER")
    if not provider:
        if os.getenv("GEMINI_API_KEY", "").strip():
            provider = "gemini"
        elif os.getenv("OPENAI_API_KEY", "").strip():
            provider = "openai"
        else:
            provider = "mock"

    provider = provider.lower().strip()
    if provider == "openai":
        client: BaseLLMClient = OpenAILLMClient()
        if fail_closed_to_mock and not client.is_configured:
            return MockLLMClient()
        return client
    if provider == "gemini":
        client = GeminiLLMClient()
        if fail_closed_to_mock and not client.is_configured:
            return MockLLMClient()
        return client
    return MockLLMClient()
