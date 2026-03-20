import abc
import json
import os
import re

import requests
from google import genai

try:
    import ollama
except ModuleNotFoundError:  # pragma: no cover - depends on optional dependency
    class _MissingOllama:
        class Client:
            def __init__(self, *args, **kwargs):
                raise ModuleNotFoundError(
                    "ollama package is required for OllamaClient. Install with `pip install ollama`."
                )

    ollama = _MissingOllama()


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

    def analyze_pr_closure(self, persona: str, mission: str, comments_context: str) -> tuple[bool, str]:
        """
        Analyze PR comments and decide if it should be closed.
        Returns (should_close, reason).
        """
        prompt = (
            f"Persona: {persona}\n"
            f"Missão: {mission}\n\n"
            f"Abaixo estão os comentários de um Pull Request. "
            f"Analise se há uma solicitação clara de fechamento, código ruim ou inseguro, rejeição ou desistência por parte de um autor autorizado.\n\n"
            f"Comentários:\n{comments_context}\n\n"
            f"Responda EXATAMENTE no formato JSON:\n"
            f"{{\"should_close\": true, \"reason\": \"motivo sucinto em português\"}}\n"
            f"ou\n"
            f"{{\"should_close\": false, \"reason\": \"\"}}"
        )

        response_text = self.generate(prompt)

        # Simple extraction of JSON if the LLM wraps it in markdown
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                return bool(data.get("should_close", False)), str(data.get("reason", ""))
            except Exception:
                pass

        # Fallback if JSON parsing fails
        if "true" in response_text.lower() or "\"should_close\": true" in response_text.lower():
            return True, "Identificado motivo para fechamento (parsing fallback)"

        return False, ""

    def _extract_code_block(self, text: str) -> str:
        """Extract the first fenced code block from markdown; return original text if none found."""
        if not text:
            return "\n"

        start_idx = text.find("```")
        if start_idx == -1:
            return text.strip() + "\n"

        # Find the end of the opening backticks line
        first_newline_idx = text.find("\n", start_idx)

        # Find the closing backticks
        end_idx = text.find("```", start_idx + 3)
        if end_idx == -1:
            # If no closing backticks, return everything after the opening ones
            if first_newline_idx != -1:
                return text[first_newline_idx+1:].strip() + "\n"
            return text[start_idx+3:].strip() + "\n"

        # Check if the opening backticks line is just an identifier or has code
        if first_newline_idx != -1 and first_newline_idx < end_idx:
            line_content = text[start_idx+3:first_newline_idx].strip()
            # If it has more than just an identifier, it might be an inline block missing a newline
            if " " in line_content or "(" in line_content or "=" in line_content:
                # It's an inline code block that happens to have a newline somewhere later
                pass
            else:
                # It is a normal block with an identifier (or empty), return what's inside
                content = text[first_newline_idx+1:end_idx]
                return content.strip() + "\n"

        # Inline code block format like ```code``` or ```print('test')\n```
        content = text[start_idx+3:end_idx]
        return content.strip() + "\n"


class GeminiClient(AIClient):
    """
    AI Client implementation for Google's Gemini models.
    """
    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        self.model = model
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def generate(self, prompt: str) -> str:
        if not self.client:
            raise ValueError("GEMINI_API_KEY is required for GeminiClient")
        response = self.client.models.generate_content(model=self.model, contents=prompt)
        text = response.text if response.text is not None else ""
        return text.strip()

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
        text = response.text if response.text is not None else ""
        return self._extract_code_block(text)

    def generate_pr_comment(self, issue_description: str) -> str:
        if not self.client:
            raise ValueError("GEMINI_API_KEY is required for GeminiClient")

        prompt = f"You are a friendly CI assistant. The pipeline failed with the following error: {issue_description}. Please write a comment for the PR author asking them to correct these issues."
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )
        text = response.text if response.text is not None else ""
        return text.strip()

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
        response = self.client.generate(model=self.model, prompt=prompt, stream=False)  # pyright: ignore[reportAttributeAccessIssue]
        return response.get("response", "").strip() if isinstance(response, dict) else getattr(response, "response", "").strip()

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

def get_ai_client(provider: str = "ollama", **kwargs) -> AIClient:
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
