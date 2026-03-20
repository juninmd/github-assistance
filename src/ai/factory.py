from src.ai.base import AIClient
from src.ai.gemini import GeminiClient
from src.ai.ollama import OllamaClient
from src.ai.openai import OpenAIClient


def get_ai_client(provider: str = "ollama", **kwargs) -> AIClient:
    """Factory to get the appropriate AI client."""
    provider_lower = provider.lower()
    if provider_lower == "gemini":
        return GeminiClient(**kwargs)
    if provider_lower == "ollama":
        return OllamaClient(**kwargs)
    if provider_lower == "openai":
        return OpenAIClient(**kwargs)
    raise ValueError(f"Unknown AI provider: {provider}")
