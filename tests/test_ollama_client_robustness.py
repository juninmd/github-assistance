import unittest
from unittest.mock import MagicMock, patch
from src.ai_client import OllamaClient, GeminiClient

class TestOllamaClientRobustness(unittest.TestCase):
    def setUp(self):
        self.client = OllamaClient()

    @patch("requests.post")
    def test_resolve_conflict_standard_block(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "```python\nprint('hello')\n```"}
        mock_post.return_value = mock_response

        result = self.client.resolve_conflict("ctx", "con")
        self.assertEqual(result, "print('hello')\n")

    @patch("requests.post")
    def test_resolve_conflict_spaced_block(self, mock_post):
        # Test with spaces instead of newline
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "```python   print('hello')\n```"}
        mock_post.return_value = mock_response

        result = self.client.resolve_conflict("ctx", "con")
        self.assertEqual(result, "print('hello')\n")

    @patch("requests.post")
    def test_resolve_conflict_no_block(self, mock_post):
        # Test with plain text
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "print('hello')"}
        mock_post.return_value = mock_response

        result = self.client.resolve_conflict("ctx", "con")
        self.assertEqual(result, "print('hello')\n")

    @patch("requests.post")
    def test_resolve_conflict_mixed_content(self, mock_post):
        # Test with mixed content (regex fails, returns full text)
        content = "Here is the code:\nprint('hello')"
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": content}
        mock_post.return_value = mock_response

        result = self.client.resolve_conflict("ctx", "con")
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
