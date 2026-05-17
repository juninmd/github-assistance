"""Tests for the modular AI package."""
import unittest
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.ai import AIClient, GeminiClient, OllamaClient, OpenAIClient, get_ai_client


class DummyClient(AIClient):
    def resolve_conflict(self, file_content: str, conflict_block: str) -> str:
        return ""
    def generate_pr_comment(self, issue_description: str) -> str:
        return f"Dummy comment: {issue_description}"


class TestAIClientBase(unittest.TestCase):
    def test_ai_client_generate_fallback(self):
        client = DummyClient()
        self.assertEqual(client.generate("test prompt"), "Dummy comment: test prompt")

    def test_ai_client_extract_code_block(self):
        client = DummyClient()
        text = "Here is the code:\n```python\nprint('hello')\n```"
        self.assertEqual(client._extract_code_block(text), "print('hello')\n")

        text_no_block = "Just some text"
        self.assertEqual(client._extract_code_block(text_no_block), "Just some text\n")

    def test_ai_client_analyze_pr_closure_json(self):
        client = DummyClient()
        client.generate = MagicMock(return_value='```json\n{"should_close": true, "reason": "test reason"}\n```')
        should_close, reason = client.analyze_pr_closure("persona", "mission", "comments")
        self.assertTrue(should_close)
        self.assertEqual(reason, "test reason")

    def test_ai_client_analyze_pr_closure_fallback(self):
        client = DummyClient()
        client.generate = MagicMock(return_value='"should_close": true')
        should_close, reason = client.analyze_pr_closure("persona", "mission", "comments")
        self.assertTrue(should_close)
        self.assertIn("Identificado motivo para fechamento", reason)

    def test_ai_client_classify_secret_finding_json(self):
        client = DummyClient()
        client.generate = MagicMock(
            return_value='```json\n{"action": "REMOVE_FROM_HISTORY", "reason": "real credential"}\n```'
        )
        result = client.classify_secret_finding(
            {"rule_id": "generic-api-key", "file": "app.env", "line": 3},
            redacted_context='> 3: API_KEY = "<redacted>"',
        )
        self.assertEqual(result, {"action": "REMOVE_FROM_HISTORY", "reason": "real credential"})


class TestAIFactory(unittest.TestCase):
    @patch("src.ai.gemini.genai.Client")
    def test_get_gemini_client(self, mock_genai):
        client = get_ai_client("gemini", api_key="fake")
        self.assertIsInstance(client, GeminiClient)

    @patch("src.ai.ollama.ollama.Client")
    def test_get_ollama_client(self, mock_ollama):
        client = get_ai_client("ollama", base_url="http://localhost:11434")
        self.assertIsInstance(client, OllamaClient)

    def test_get_openai_client(self):
        client = get_ai_client("openai", api_key="fake")
        self.assertIsInstance(client, OpenAIClient)

    def test_unknown_provider_raises_error(self):
        with self.assertRaises(ValueError):
            get_ai_client("unknown")


class TestProviderClients(unittest.TestCase):
    @patch("src.ai.gemini.genai.Client")
    def test_gemini_generate(self, mock_genai_client):
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance
        mock_response = MagicMock()
        mock_response.text = "test response"
        mock_client_instance.models.generate_content.return_value = mock_response

        client = GeminiClient(api_key="test_key")
        self.assertEqual(client.generate("test"), "test response")

    @patch("src.ai.ollama.ollama.Client")
    def test_ollama_generate(self, mock_ollama_client):
        mock_client_instance = MagicMock()
        mock_ollama_client.return_value = mock_client_instance
        mock_response = MagicMock()
        mock_response.response = "test response"
        mock_client_instance.generate.return_value = mock_response

        client = OllamaClient()
        self.assertEqual(client.generate("test"), "test response")

    @patch("src.ai.ollama.ollama.Client")
    def test_ollama_uses_timeout_ms_env(self, mock_ollama_client):
        with patch.dict("os.environ", {"OLLAMA_TIMEOUT_MS": "120000"}):
            client = OllamaClient(base_url="http://localhost:11434/")

        self.assertEqual(client.base_url, "http://localhost:11434")
        self.assertEqual(client.timeout, 120)
        mock_ollama_client.assert_called_with(host="http://localhost:11434", timeout=120)

    @patch("src.ai.openai.requests.post")
    def test_openai_generate(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "test response"}}]}
        mock_post.return_value = mock_response

        client = OpenAIClient(api_key="test_key")
        self.assertEqual(client.generate("test"), "test response")


if __name__ == "__main__":
    unittest.main()
