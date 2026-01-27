import unittest
from unittest.mock import MagicMock, patch
import os
from src.ai_client import GeminiClient

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
        self.assertEqual(kwargs['model'], 'gemini-1.5-pro')
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
        self.assertEqual(kwargs['model'], 'gemini-1.5-pro')
        self.assertEqual(result, "Comment")

if __name__ == '__main__':
    unittest.main()
