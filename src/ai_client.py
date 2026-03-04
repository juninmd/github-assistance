import abc
import os
import re

import ollama
import requests
from google import genai


class AIClient(abc.ABC):
    @abc.abstractmethod
    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        """Resolve a git merge conflict given the full file context and conflict block."""
        pass  # pragma: no cover

    @abc.abstractmethod
    def generate_pr_comment(self, issue_description: str) -> str:
        """Generate a PR comment explaining a pipeline/issue failure."""
        pass  # pragma: no cover

    def generate(self, prompt: str) -> str:
        """General-purpose text generation (concrete clients should override)."""
        return self.generate_pr_comment(prompt)  # default fallback

    def _extract_code_block(self, text: str) -> str:
        """Extract the first fenced code block from markdown; return original text if none found."""
        match = re.search(r"```(?:\w+)?\s+(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1)
        return text.rstrip() + "\n"


class GeminiClient(AIClient):
    """
    AI Client implementation for Google's Gemini models.
    """
    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def generate(self, prompt: str) -> str:
        if not self.client:
            raise ValueError("GEMINI_API_KEY is required for GeminiClient")
        response = self.client.models.generate_content(model=self.model, contents=prompt)
        return response.text.strip()

    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        if not self.client:
            raise ValueError("GEMINI_API_KEY is required for GeminiClient")
        prompt = (
            f"You are an expert software engineer. Resolve the following git merge conflict.\n"
            f"Here is the context of the file:\n```\n{file_content}\n```\n"
            f"Here is the conflict block:\n```\n{conflict_block}\n```\n"
            f"Return ONLY the resolved code for the conflict block, without markers or markdown formatting."
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )
        return self._extract_code_block(response.text)

    def generate_pr_comment(self, issue_description: str) -> str:
        if not self.client:
            raise ValueError("GEMINI_API_KEY is required for GeminiClient")

        prompt = f"You are a friendly CI assistant. The pipeline failed with the following error: {issue_description}. Please write a comment for the PR author asking them to correct these issues."
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )
        return response.text.strip()

class OllamaClient(AIClient):
    """
    AI Client implementation for local Ollama models.
    """
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url
        self.model = model
        self.client = ollama.Client(host=self.base_url)

    def _generate(self, prompt: str) -> str:
        """
        Internal method to generate text using Ollama SDK.
        """
        response = self.client.generate(model=self.model, prompt=prompt, stream=False)
        return response.get("response", "").strip()

    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        prompt = (
            f"You are an expert software engineer. Resolve the following git merge conflict.\n"
            f"Here is the context of the file:\n```\n{file_content}\n```\n"
            f"Here is the conflict block:\n```\n{conflict_block}\n```\n"
            f"Return ONLY the resolved code for the conflict block, without markers or markdown formatting."
        )
        text = self._generate(prompt)
        return self._extract_code_block(text)

    def generate(self, prompt: str) -> str:
        return self._generate(prompt)

    def generate_pr_comment(self, issue_description: str) -> str:
        prompt = f"Write a GitHub PR comment asking the author to fix this issue: {issue_description}"
        return self._generate(prompt)


class OpenAIClient(AIClient):
    """
    AI Client implementation for OpenAI models.
    """
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

        # Extract content from standard OpenAI Chat Completion response
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

# Alias for backward compatibility if needed, though mostly internal
OpenAICodexClient = OpenAIClient

def get_ai_client(provider: str = "gemini", **kwargs) -> AIClient:
    """
    Factory to get the appropriate AI client.
    """
    if provider.lower() == "gemini":
        return GeminiClient(**kwargs)
    elif provider.lower() == "ollama":
        return OllamaClient(**kwargs)
    elif provider.lower() == "openai":
        return OpenAIClient(**kwargs)
    else:
        raise ValueError(f"Unknown AI provider: {provider}")
