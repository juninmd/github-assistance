import unittest
from unittest.mock import MagicMock, patch
import os
from src.ai_client import GeminiClient, OllamaClient

class TestGeminiClient(unittest.TestCase):
    def setUp(self):
        # Prevent actual API key requirement if we mock it
        self.api_key = "fake_key"

    @patch("src.ai_client.genai.Client")
    def test_initialization(self, mock_client_cls):
        client = GeminiClient(api_key=self.api_key)
        mock_client_cls.assert_called_with(api_key=self.api_key)
        self.assertEqual(client.client, mock_client_cls.return_value)

    @patch("src.ai_client.genai.Client")
    def test_resolve_conflict(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_response = MagicMock()
        mock_response.text = "Resolved Code"
        mock_instance.models.generate_content.return_value = mock_response

        client = GeminiClient(api_key=self.api_key)
        result = client.resolve_conflict("content", "conflict")

        mock_instance.models.generate_content.assert_called_once()
        args, kwargs = mock_instance.models.generate_content.call_args
        self.assertEqual(kwargs['model'], 'gemini-2.5-flash')
        self.assertIn("content", kwargs['contents'])
        self.assertEqual(result, "Resolved Code\n")

    @patch("src.ai_client.genai.Client")
    def test_generate_pr_comment(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_response = MagicMock()
        mock_response.text = "Comment"
        mock_instance.models.generate_content.return_value = mock_response

        client = GeminiClient(api_key=self.api_key)
        result = client.generate_pr_comment("issue")

        mock_instance.models.generate_content.assert_called_once()
        args, kwargs = mock_instance.models.generate_content.call_args
        self.assertEqual(kwargs['model'], 'gemini-2.5-flash')
        self.assertEqual(result, "Comment")

class TestOllamaClient(unittest.TestCase):
    def setUp(self):
        self.client = OllamaClient(base_url="http://mock-url", model="mock-model")

    @patch("src.ai_client.requests.post")
    def test_resolve_conflict(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "```python\nprint('hello')\n```"}
        mock_post.return_value = mock_response

        result = self.client.resolve_conflict("context", "conflict")

        self.assertEqual(result, "print('hello')\n")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['model'], "mock-model")
        self.assertIn("Resolve this git merge conflict", kwargs['json']['prompt'])

    @patch("src.ai_client.requests.post")
    def test_generate_pr_comment(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Fix the bugs"}
        mock_post.return_value = mock_response

        result = self.client.generate_pr_comment("pipeline failed")

        self.assertEqual(result, "Fix the bugs")
        mock_post.assert_called_once()
        self.assertIn("pipeline failed", mock_post.call_args[1]['json']['prompt'])

    @patch("src.ai_client.requests.post")
    def test_error_handling(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("Connection refused")

        result = self.client.generate_pr_comment("issue")
        self.assertEqual(result, "")

if __name__ == '__main__':
    unittest.main()
