import warnings

from src.ai import (
    AIClient,
    GeminiClient,
    OllamaClient,
    OpenAIClient,
    OpenAICodexClient,
    get_ai_client,
)

warnings.warn(
    "src/ai_client is deprecated; use src.ai instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "AIClient",
    "GeminiClient",
    "OllamaClient",
    "OpenAIClient",
    "OpenAICodexClient",
    "get_ai_client",
]
