import os
import requests
from src.ai.base import AIClient


class OpenAIClient(AIClient):
    """AI Client implementation for OpenAI models."""
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.base_url = "https://api.openai.com/v1/chat/completions"

    def _generate(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIClient")
        response = requests.post(
            self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        try:
            return payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            return ""

    def generate(self, prompt: str) -> str:
        return self._generate(prompt)

    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        prompt = (
            "You are an expert software engineer. Resolve the git merge conflict below. "
            "Return only the resolved code, without markdown fences.\n\n"
            f"File context:\n{file_content}\n\n"
            f"Conflict block:\n{conflict_block}"
        )
        text = self._generate(prompt)
        return self._extract_code_block(text)

    def generate_pr_comment(self, issue_description: str) -> str:
        prompt = (
            "You are a friendly CI assistant. Write a concise GitHub PR comment asking the "
            "author to fix the following pipeline issue:\n"
            f"{issue_description}"
        )
        return self._generate(prompt)


# Alias for backward compatibility
OpenAICodexClient = OpenAIClient
