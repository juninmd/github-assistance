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
    @patch("src.ai_client.ollama.Client")
    def test_resolve_conflict(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_instance.generate.return_value = {"response": "```\nresolved\n```"}

        client = OllamaClient()
        result = client.resolve_conflict("ctx", "con")
        self.assertEqual(result, "resolved\n")

        mock_instance.generate.assert_called_with(model="llama3", prompt=ANY, stream=False)

    @patch("src.ai_client.ollama.Client")
    def test_generate_pr_comment(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_instance.generate.return_value = {"response": "Comment"}

        client = OllamaClient()
        result = client.generate_pr_comment("issue")
        self.assertEqual(result, "Comment")

    @patch("src.ai_client.ollama.Client")
    def test_request_exception(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_instance.generate.side_effect = Exception("Error")

        client = OllamaClient()
        with self.assertRaises(Exception):
            client.generate_pr_comment("issue")
