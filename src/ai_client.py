import os
import abc
import re
import requests
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
        pass

    @abc.abstractmethod
    def generate_pr_comment(self, issue_description: str) -> str:
        """
        Generates a comment to post on a PR (e.g., explaining why pipeline failed).
        """
        pass

class GeminiClient(AIClient):
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required for GeminiClient")
        self.client = genai.Client(api_key=self.api_key)

    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        prompt = (
            f"You are an expert software engineer. Resolve the following git merge conflict.\n"
            f"Here is the context of the file:\n```\n{file_content}\n```\n"
            f"Here is the conflict block:\n```\n{conflict_block}\n```\n"
            f"Return ONLY the resolved code for the conflict block, without markers or markdown formatting."
        )
        response = self.client.models.generate_content(
            model='gemini-1.5-pro',
            contents=prompt
        )
        text = response.text
        # Extract code block if present
        match = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1)
        return text.rstrip() + "\n"

    def generate_pr_comment(self, issue_description: str) -> str:
        prompt = f"You are a friendly CI assistant. The pipeline failed with the following error: {issue_description}. Please write a comment for the PR author asking them to correct these issues."
        response = self.client.models.generate_content(
            model='gemini-1.5-pro',
            contents=prompt
        )
        return response.text.strip()

class OllamaClient(AIClient):
    def __init__(self, base_url="http://localhost:11434", model="llama3"):
        self.base_url = base_url
        self.model = model

    def _generate(self, prompt: str) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False}
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except requests.RequestException as e:
            print(f"Error communicating with Ollama: {e}")
            return ""

    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        prompt = (
            f"Resolve this git merge conflict. Return ONLY the resolved code.\n"
            f"Context: {file_content}\n"
            f"Conflict: {conflict_block}"
        )
        text = self._generate(prompt)
        # Extract code block if present
        match = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1)
        return text.rstrip() + "\n"

    def generate_pr_comment(self, issue_description: str) -> str:
        prompt = f"Write a GitHub PR comment asking the author to fix this issue: {issue_description}"
        return self._generate(prompt)
