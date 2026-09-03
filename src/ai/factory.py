"""AI client factory — only the cluster LiteLLM proxy is allowed."""

from src.ai.base import AIClient
from src.ai.litellm_client import LiteLLMClient


def get_ai_client(provider: str = "litellm", **kwargs) -> AIClient:
    """Build an AI client.

    ``provider`` is ignored for compatibility — every provider resolves to the
    OpenAI-compatible LiteLLM proxy on the cluster.
    """
    return LiteLLMClient(**kwargs)
