from src.ai.base import AIClient
from src.ai.gemini import GeminiClient
from src.ai.litellm_client import LiteLLMClient
from src.ai.ollama import OllamaClient
from src.ai.openai import OpenAIClient


def get_ai_client(provider: str = "ollama", **kwargs) -> AIClient:
    """Factory to get the appropriate AI client."""
    match provider.lower():
        case "gemini":
            return GeminiClient(**kwargs)
        case "litellm":
            return LiteLLMClient(**kwargs)
        case "ollama":
            return OllamaClient(**kwargs)
        case "openai":
            return OpenAIClient(**kwargs)
        case _:
            raise ValueError(f"Unknown AI provider: {provider}")
