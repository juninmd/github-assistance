import unittest
from unittest.mock import MagicMock, patch, ANY
import os
import requests
from src.ai_client import get_ai_client, GeminiClient, OllamaClient

class TestAIClient(unittest.TestCase):
    def test_get_ai_client(self):
        # Patch GeminiClient to avoid initializing real Google GenAI client
        with patch("src.ai_client.GeminiClient"):
            self.assertIsInstance(get_ai_client("gemini", api_key="test"), MagicMock)

        self.assertIsInstance(get_ai_client("ollama"), OllamaClient)

        with self.assertRaises(ValueError):
            get_ai_client("unknown")

class TestGeminiClient(unittest.TestCase):
    def test_init_no_key(self):
        with patch.dict(os.environ, {}, clear=True):
            client = GeminiClient(api_key=None)
            self.assertIsNone(client.client)

    def test_init_with_key(self):
        with patch("google.genai.Client") as mock_client:
            client = GeminiClient(api_key="test_key")
            mock_client.assert_called_with(api_key="test_key")
            self.assertIsNotNone(client.client)

    def test_resolve_conflict(self):
        with patch("google.genai.Client") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.models.generate_content.return_value.text = "```python\nresolved_code\n```"

            client = GeminiClient(api_key="test")
            result = client.resolve_conflict("context", "conflict")

            self.assertEqual(result, "resolved_code\n")
            mock_instance.models.generate_content.assert_called_once()

    def test_resolve_conflict_no_code_block(self):
        with patch("google.genai.Client") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.models.generate_content.return_value.text = "resolved_code_no_block"

            client = GeminiClient(api_key="test")
            result = client.resolve_conflict("context", "conflict")

            self.assertEqual(result, "resolved_code_no_block\n")

    def test_resolve_conflict_no_client(self):
        client = GeminiClient(api_key=None)
        with self.assertRaises(ValueError):
            client.resolve_conflict("a", "b")

    def test_generate_pr_comment(self):
        with patch("google.genai.Client") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.models.generate_content.return_value.text = "Fix it"

            client = GeminiClient(api_key="test")
            result = client.generate_pr_comment("error")

            self.assertEqual(result, "Fix it")

    def test_generate_pr_comment_no_client(self):
        client = GeminiClient(api_key=None)
        with self.assertRaises(ValueError):
            client.generate_pr_comment("error")

class TestOllamaClient(unittest.TestCase):
    @patch("requests.post")
    def test_resolve_conflict(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "```\nresolved\n```"}
        mock_post.return_value = mock_response

        client = OllamaClient()
        result = client.resolve_conflict("ctx", "con")
        self.assertEqual(result, "resolved\n")

        mock_post.assert_called_with(
            "http://localhost:11434/api/generate",
            json={"model": "llama3", "prompt": ANY, "stream": False}
        )

    @patch("requests.post")
    def test_generate_pr_comment(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Comment"}
        mock_post.return_value = mock_response

        client = OllamaClient()
        result = client.generate_pr_comment("issue")
        self.assertEqual(result, "Comment")

    @patch("requests.post")
    def test_request_exception(self, mock_post):
        mock_post.side_effect = requests.RequestException("Error")

        client = OllamaClient()
        result = client.generate_pr_comment("issue")
        self.assertEqual(result, "")
