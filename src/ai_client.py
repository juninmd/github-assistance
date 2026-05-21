"""
Compatibility shim — re-exports from the refactored src.ai package.
"""
from src.ai import AIClient, GeminiClient, OllamaClient, OpenAIClient, get_ai_client

__all__ = [
    "AIClient",
    "GeminiClient",
    "OllamaClient",
    "OpenAIClient",
    "get_ai_client",
]
