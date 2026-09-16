import os
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
