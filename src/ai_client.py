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


_CONFLICT_RESOLUTION_PROMPT = (
    "You are an expert software engineer. Resolve the following git merge conflict.\n"
    "Here is the context of the file:\n```\n{file_content}\n```\n"
    "Here is the conflict block:\n```\n{conflict_block}\n```\n"
    "Return ONLY the resolved code for the conflict block, without markers or markdown formatting."
)


class AIClient(abc.ABC):
    @abc.abstractmethod
    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        pass  # pragma: no cover

    @abc.abstractmethod
    def generate_pr_comment(self, issue_description: str) -> str:
        pass  # pragma: no cover

    def generate(self, prompt: str) -> str:
        return self.generate_pr_comment(prompt)

    def analyze_pr_closure(
        self, persona: str, mission: str, comments_context: str
    ) -> tuple[bool, str]:
        prompt = (
            f"Persona: {persona}\n"
            f"Missão: {mission}\n\n"
            f"Abaixo estão os comentários de um Pull Request. "
            f"Analise se há uma solicitação clara de fechamento, código ruim ou inseguro, rejeição ou desistência por parte de um autor autorizado.\n\n"
            f"Comentários:\n{comments_context}\n\n"
            f"Responda EXATAMENTE no formato JSON:\n"
            f'{{"should_close": true, "reason": "motivo sucinto em português"}}\n'
            f"ou\n"
            f'{{"should_close": false, "reason": ""}}'
        )

        response_text = self.generate(prompt)

        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                return bool(data.get("should_close", False)), str(data.get("reason", ""))
            except Exception:
                pass

        if "true" in response_text.lower() or '"should_close": true' in response_text.lower():
            return True, "Identificado motivo para fechamento (parsing fallback)"

        return False, ""

    @staticmethod
    def _is_language_id(s: str) -> bool:
        return bool(re.match(r'^[a-zA-Z0-9_+-]+$', s))

    def _extract_code_block(self, text: str) -> str:
        if not text:
            return "\n"

        start = text.find("```")
        if start == -1:
            return text.strip() + "\n"

        newline_after = text.find("\n", start)
        end = text.find("```", start + 3)

        if end == -1:
            if newline_after != -1:
                return text[newline_after + 1:].strip() + "\n"
            return text[start + 3:].strip() + "\n"

        if newline_after != -1 and newline_after < end:
            line_content = text[start + 3:newline_after].strip()
            if not line_content or self._is_language_id(line_content):
                return text[newline_after + 1:end].strip() + "\n"

        content = text[start + 3:end]
        return content.strip() + "\n"


class GeminiClient(AIClient):
    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        self.model = model
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    def _call_gemini(self, prompt: str) -> str:
        if not self.client:
            raise ValueError("GEMINI_API_KEY is required for GeminiClient")
        response = self.client.models.generate_content(model=self.model, contents=prompt)
        text = response.text if response.text is not None else ""
        return text.strip()

    def generate(self, prompt: str) -> str:
        return self._call_gemini(prompt)

    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        prompt = _CONFLICT_RESOLUTION_PROMPT.format(
            file_content=file_content, conflict_block=conflict_block
        )
        return self._extract_code_block(self._call_gemini(prompt))

    def generate_pr_comment(self, issue_description: str) -> str:
        prompt = (
            f"You are a friendly CI assistant. The pipeline failed with the following error: "
            f"{issue_description}. Please write a comment for the PR author asking them to correct these issues."
        )
        return self._call_gemini(prompt)


class OllamaClient(AIClient):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url
        self.model = model
        self.client = ollama.Client(host=self.base_url)

    def _generate(self, prompt: str) -> str:
        response = self.client.generate(model=self.model, prompt=prompt, stream=False)
        return (
            response.get("response", "").strip()
            if isinstance(response, dict)
            else getattr(response, "response", "").strip()
        )

    def generate(self, prompt: str) -> str:
        return self._generate(prompt)

    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        prompt = _CONFLICT_RESOLUTION_PROMPT.format(
            file_content=file_content, conflict_block=conflict_block
        )
        return self._extract_code_block(self._generate(prompt))

    def generate_pr_comment(self, issue_description: str) -> str:
        prompt = (
            f"Write a GitHub PR comment asking the author to fix this issue: {issue_description}"
        )
        return self._generate(prompt)


class OpenAIClient(AIClient):
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
        prompt = _CONFLICT_RESOLUTION_PROMPT.format(
            file_content=file_content, conflict_block=conflict_block
        )
        return self._extract_code_block(self._generate(prompt))

    def generate_pr_comment(self, issue_description: str) -> str:
        prompt = (
            "You are a friendly CI assistant. Write a concise GitHub PR comment asking the "
            "author to fix the following pipeline issue:\n"
            f"{issue_description}"
        )
        return self._generate(prompt)


def get_ai_client(provider: str = "ollama", **kwargs) -> AIClient:
    if provider.lower() == "gemini":
        return GeminiClient(**kwargs)
    elif provider.lower() == "ollama":
        return OllamaClient(**kwargs)
    elif provider.lower() == "openai":
        return OpenAIClient(**kwargs)
    else:
        raise ValueError(f"Unknown AI provider: {provider}")
