import unittest
from unittest.mock import MagicMock, patch

from src.ai_client import GeminiClient, OllamaClient


class TestOllamaClientRobustness(unittest.TestCase):
    @patch("src.ai_client.ollama.Client")
    def test_resolve_conflict_standard_block(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_instance.generate.return_value = {"response": "```python\nprint('hello')\n```"}

        client = OllamaClient()
        result = client.resolve_conflict("ctx", "con")
        self.assertEqual(result, "print('hello')\n")

    @patch("src.ai_client.ollama.Client")
    def test_resolve_conflict_spaced_block(self, mock_client_cls):
        # Test with spaces instead of newline
        mock_instance = mock_client_cls.return_value
        mock_instance.generate.return_value = {"response": "```python   print('hello')\n```"}

        client = OllamaClient()
        result = client.resolve_conflict("ctx", "con")
        self.assertEqual(result, "print('hello')\n")

    @patch("src.ai_client.ollama.Client")
    def test_resolve_conflict_no_block(self, mock_client_cls):
        # Test with plain text
        mock_instance = mock_client_cls.return_value
        mock_instance.generate.return_value = {"response": "print('hello')"}

        client = OllamaClient()
        result = client.resolve_conflict("ctx", "con")
        self.assertEqual(result, "print('hello')\n")

    @patch("src.ai_client.ollama.Client")
    def test_resolve_conflict_mixed_content(self, mock_client_cls):
        # Test with mixed content (regex fails, returns full text)
        content = "Here is the code:\nprint('hello')"
        mock_instance = mock_client_cls.return_value
        mock_instance.generate.return_value = {"response": content}

        client = OllamaClient()
        result = client.resolve_conflict("ctx", "con")
        self.assertEqual(result, content.rstrip() + "\n")

class TestGeminiClientRobustness(unittest.TestCase):
    @patch("google.genai.Client")
    def test_resolve_conflict_spaced_block(self, mock_cls):
        # Initialize client inside the test where patch is active
        self.client = GeminiClient(api_key="test")

        mock_instance = mock_cls.return_value
        mock_instance.models.generate_content.return_value.text = "```python   print('gemini')\n```"

        result = self.client.resolve_conflict("ctx", "con")
        self.assertEqual(result, "print('gemini')\n")
