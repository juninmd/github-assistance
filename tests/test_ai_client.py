import unittest
from unittest.mock import MagicMock, patch
import os
import requests
from src.ai_client import GeminiClient, OllamaClient, OpenAICodexClient, get_ai_client

class TestGeminiClient(unittest.TestCase):
    def setUp(self):
        self.api_key = "fake_key"

    @patch("src.ai_client.genai.Client")
    def test_initialization(self, mock_client_cls):
        client = GeminiClient(api_key=self.api_key, model="gemini-pro")
        mock_client_cls.assert_called_with(api_key=self.api_key)
        self.assertEqual(client.model, "gemini-pro")

    @patch("src.ai_client.genai.Client")
    def test_resolve_conflict(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_response = MagicMock()
        mock_response.text = "Resolved Code"
        mock_instance.models.generate_content.return_value = mock_response

        client = GeminiClient(api_key=self.api_key)
        result = client.resolve_conflict("content", "conflict")

        # Verify model used is default
        self.assertEqual(client.model, "gemini-2.5-flash")

        args, kwargs = mock_instance.models.generate_content.call_args
        self.assertEqual(kwargs['model'], 'gemini-2.5-flash')
        self.assertEqual(result, "Resolved Code\n")

    @patch("src.ai_client.genai.Client")
    def test_resolve_conflict_with_block(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_response = MagicMock()
        mock_response.text = "Here is code:\n```python\nprint('hello')\n```"
        mock_instance.models.generate_content.return_value = mock_response

        client = GeminiClient(api_key=self.api_key)
        result = client.resolve_conflict("content", "conflict")
        self.assertEqual(result, "print('hello')\n")

    @patch("src.ai_client.genai.Client")
    def test_resolve_conflict_custom_model(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_response = MagicMock()
        mock_response.text = "Resolved Code"
        mock_instance.models.generate_content.return_value = mock_response

        client = GeminiClient(api_key=self.api_key, model="custom-model")
        result = client.resolve_conflict("content", "conflict")

        args, kwargs = mock_instance.models.generate_content.call_args
        self.assertEqual(kwargs['model'], 'custom-model')

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

    def test_missing_api_key_resolve_conflict(self):
        with patch.dict(os.environ, {}, clear=True):
             client = GeminiClient()
             self.assertIsNone(client.client)
             with self.assertRaises(ValueError):
                 client.resolve_conflict("a", "b")

    def test_missing_api_key_generate_pr_comment(self):
        with patch.dict(os.environ, {}, clear=True):
             client = GeminiClient()
             self.assertIsNone(client.client)
             with self.assertRaises(ValueError):
                 client.generate_pr_comment("issue")

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
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['model'], "mock-model")
        self.assertEqual(self.client.base_url, "http://mock-url")

    @patch("src.ai_client.requests.post")
    def test_resolve_conflict_no_block(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Just code"}
        mock_post.return_value = mock_response

        result = self.client.resolve_conflict("context", "conflict")
        self.assertEqual(result, "Just code\n")

    @patch("src.ai_client.requests.post")
    def test_generate_pr_comment(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Fix the bugs"}
        mock_post.return_value = mock_response

        result = self.client.generate_pr_comment("pipeline failed")
        self.assertEqual(result, "Fix the bugs")

    @patch("src.ai_client.requests.post")
    def test_error_handling(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("Connection refused")

        with self.assertRaises(requests.RequestException):
             self.client.generate_pr_comment("issue")


class TestOpenAICodexClient(unittest.TestCase):
    @patch("src.ai_client.requests.post")
    def test_generate_pr_comment(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "output": [{"content": [{"type": "output_text", "text": "Please fix CI errors"}]}]
        }
        mock_post.return_value = mock_response

        client = OpenAICodexClient(api_key="openai-key", model="gpt-5-codex")
        result = client.generate_pr_comment("test issue")

        self.assertEqual(result, "Please fix CI errors")

    @patch("src.ai_client.requests.post")
    def test_resolve_conflict(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "output": [{"content": [{"type": "output_text", "text": "```python\nprint('ok')\n```"}]}]
        }
        mock_post.return_value = mock_response

        client = OpenAICodexClient(api_key="openai-key", model="gpt-5-codex")
        result = client.resolve_conflict("context", "conflict")
        self.assertEqual(result, "print('ok')\n")

    def test_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            client = OpenAICodexClient()
            with self.assertRaises(ValueError):
                client.generate_pr_comment("issue")

class TestAIClientFactory(unittest.TestCase):
    def test_get_gemini(self):
        client = get_ai_client("gemini", api_key="test", model="test-model")
        self.assertIsInstance(client, GeminiClient)
        self.assertEqual(client.model, "test-model")

    def test_get_ollama(self):
        client = get_ai_client("ollama", base_url="http://test", model="test-model")
        self.assertIsInstance(client, OllamaClient)
        self.assertEqual(client.model, "test-model")
        self.assertEqual(client.base_url, "http://test")

    def test_get_openai(self):
        client = get_ai_client("openai", api_key="openai-key", model="gpt-5-codex")
        self.assertIsInstance(client, OpenAICodexClient)
        self.assertEqual(client.model, "gpt-5-codex")

    def test_unknown_provider(self):
        with self.assertRaises(ValueError):
            get_ai_client("unknown")

if __name__ == '__main__':
    unittest.main()
