"""
AI client package — all traffic goes through the OpenAI-compatible LiteLLM proxy.
"""

from src.ai.base import AIClient
from src.ai.factory import get_ai_client
from src.ai.litellm_client import LiteLLMClient

__all__ = ["AIClient", "LiteLLMClient", "get_ai_client"]
