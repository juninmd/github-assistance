import os
from typing import Any
from src.ai.base import AIClient

try:
    import ollama
except ModuleNotFoundError:  # pragma: no cover
    class _MissingOllama:
        class Client:
            def __init__(self, *args, **kwargs):
                raise ModuleNotFoundError(
                    "ollama package is required for OllamaClient. Install with `pip install ollama`."
                )
            def generate(self, *args, **kwargs) -> Any:
                pass
    ollama = _MissingOllama()


class OllamaClient(AIClient):
    """AI Client implementation for local Ollama models."""
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url
        self.model = model
        self.client = ollama.Client(host=self.base_url, timeout=300)

    def _generate(self, prompt: str) -> str:
        response = self.client.generate(model=self.model, prompt=prompt, stream=False)
        return response.response.strip()

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
        text = self._generate(prompt)
        return self._extract_code_block(text)

    def generate(self, prompt: str) -> str:
        return self._generate(prompt)

    def generate_pr_comment(self, issue_description: str) -> str:
        prompt = f"Write a GitHub PR comment asking the author to fix this issue: {issue_description}"
        return self._generate(prompt)
