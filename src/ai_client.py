import os
import abc
import re
import requests
from typing import Optional
from google import genai

class AIClient(abc.ABC):
    @abc.abstractmethod
    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        """
        Asks the AI to resolve a merge conflict.
        :param file_content: The full content of the file (context).
        :param conflict_block: The specific block with conflict markers.
        :return: The resolved content for that block.
        """
        pass  # pragma: no cover

    @abc.abstractmethod
    def generate_pr_comment(self, issue_description: str) -> str:
        """
        Generates a comment to post on a PR (e.g., explaining why pipeline failed).
        :param issue_description: The description of the pipeline failure.
        :return: The generated comment text.
        """
        pass  # pragma: no cover

class GeminiClient(AIClient):
    """
    AI Client implementation for Google's Gemini models.
    """
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

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
        text = response.text
        # Extract code block if present
        match = re.search(r"```(?:\w+)?\s+(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1)
        return text.rstrip() + "\n"

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

    def _generate(self, prompt: str) -> str:
        """
        Internal method to generate text using Ollama API.
        Raises exception on failure.
        """
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=60
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()

    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        prompt = (
            f"Resolve this git merge conflict. Return ONLY the resolved code.\n"
            f"Context: {file_content}\n"
            f"Conflict: {conflict_block}"
        )
        text = self._generate(prompt)
        # Extract code block if present
        match = re.search(r"```(?:\w+)?\s+(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1)
        return text.rstrip() + "\n"

    def generate_pr_comment(self, issue_description: str) -> str:
        prompt = f"Write a GitHub PR comment asking the author to fix this issue: {issue_description}"
        return self._generate(prompt)


class OpenAICodexClient(AIClient):
    """
    AI Client implementation for OpenAI models.
    """
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5-codex"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.base_url = "https://api.openai.com/v1/responses"

    def _generate(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAICodexClient")

        response = requests.post(
            self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": prompt,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()

        output = payload.get("output", [])
        collected_text = []
        for item in output:
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    collected_text.append(content["text"])

        if collected_text:
            return "\n".join(collected_text).strip()

        if payload.get("output_text"):
            return payload["output_text"].strip()

        return ""

    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        prompt = (
            "You are an expert software engineer. Resolve the git merge conflict below. "
            "Return only the resolved code, without markdown fences.\n\n"
            f"File context:\n{file_content}\n\n"
            f"Conflict block:\n{conflict_block}"
        )
        text = self._generate(prompt)
        match = re.search(r"```(?:\w+)?\s+(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1)
        return text.rstrip() + "\n"

    def generate_pr_comment(self, issue_description: str) -> str:
        prompt = (
            "You are a friendly CI assistant. Write a concise GitHub PR comment asking the "
            "author to fix the following pipeline issue:\n"
            f"{issue_description}"
        )
        return self._generate(prompt)

def get_ai_client(provider: str = "gemini", **kwargs) -> AIClient:
    """
    Factory to get the appropriate AI client.
    """
    if provider.lower() == "gemini":
        return GeminiClient(**kwargs)
    elif provider.lower() == "ollama":
        return OllamaClient(**kwargs)
    elif provider.lower() == "openai":
        return OpenAICodexClient(**kwargs)
    else:
        raise ValueError(f"Unknown AI provider: {provider}")
