import os

from google import genai

from src.ai.base import AIClient


class GeminiClient(AIClient):
    """AI Client implementation for Google's Gemini models."""

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
        text = response.text or ""
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
        response = self.client.models.generate_content(model=self.model, contents=prompt)
        text = response.text or ""
        return self._extract_code_block(text)

    def generate_pr_comment(self, issue_description: str) -> str:
        if not self.client:
            raise ValueError("GEMINI_API_KEY is required for GeminiClient")
        prompt = (
            f"You are a friendly CI assistant. The pipeline failed with the following error: "
            f"{issue_description}. Please write a comment for the PR author asking them to "
            f"correct these issues."
        )
        response = self.client.models.generate_content(model=self.model, contents=prompt)
        text = response.text or ""
        return text.strip()
