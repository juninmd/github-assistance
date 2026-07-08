import os
from typing import Any

from src.ai.base import AIClient

try:
    import litellm  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover

    class _MissingLiteLLM:
        def completion(self, *args: Any, **kwargs: Any) -> Any:
            raise ModuleNotFoundError(
                "litellm package is required for LiteLLMClient. Install with `pip install litellm`."
            )

    litellm = _MissingLiteLLM()  # type: ignore[assignment]


class LiteLLMClient(AIClient):
    """AI Client backed by a LiteLLM proxy (OpenAI-compatible endpoint).

    When api_base is set (proxy mode), models are addressed as bare names
    (e.g. "cloud/gemma3") and LiteLLM is called with the "openai/" prefix so it
    routes through the proxy instead of trying to resolve the provider directly.

    Direct provider mode (no api_base): pass the full provider-prefixed model
    name, e.g. "gemini/gemini-2.0-flash" or "ollama/qwen3:1.7b".
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        **kwargs: Any,
    ):
        self.model = model or os.getenv("LITELLM_MODEL") or "cloud/llama-70b"
        self.api_key = api_key or os.getenv("LITELLM_API_KEY")
        self.api_base = self._normalize_api_base(api_base or os.getenv("LITELLM_API_BASE"))
        self._extra: dict[str, Any] = kwargs

    @staticmethod
    def _normalize_api_base(api_base: str | None) -> str | None:
        if not api_base:
            return None
        normalized = api_base.rstrip("/")
        if normalized.endswith("/v1"):
            return normalized
        return f"{normalized}/v1"

    def _resolve_model(self) -> str:
        """When routing through a proxy, prefix model with 'openai/' so LiteLLM
        treats the proxy as an OpenAI-compatible backend."""
        if self.api_base and not self.model.startswith("openai/"):
            return f"openai/{self.model}"
        return self.model

    def _generate(self, prompt: str) -> str:
        call_kwargs: dict[str, Any] = {
            "model": self._resolve_model(),
            "messages": [{"role": "user", "content": prompt}],
            **self._extra,
        }
        if self.api_key:
            call_kwargs["api_key"] = self.api_key
        if self.api_base:
            call_kwargs["api_base"] = self.api_base

        response = litellm.completion(**call_kwargs)
        try:
            return response.choices[0].message.content.strip()  # type: ignore[union-attr]
        except (AttributeError, IndexError):
            return ""

    def generate(self, prompt: str) -> str:
        return self._generate(prompt)

    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        prompt = (
            "You are an expert software engineer resolving git merge conflicts.\n"
            "Your task:\n"
            "1. Analyze the conflict markers (<<<<<<< HEAD, =======, >>>>>>>) to understand both versions\n"
            "2. Apply correct logic - prefer the newer implementation unless it breaks functionality\n"
            "3. Preserve imports, dependencies, and surrounding code\n"
            f"File content:\n{file_content}\n"
            "Return ONLY the fully resolved file content with NO conflict markers, NO markdown, NO explanation."
        )
        return self._extract_code_block(self._generate(prompt))

    def generate_pr_comment(self, issue_description: str) -> str:
        prompt = (
            "You are a friendly CI assistant. Write a concise GitHub PR comment asking the "
            "author to fix the following pipeline issue:\n"
            f"{issue_description}"
        )
        return self._generate(prompt)
