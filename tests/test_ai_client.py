import unittest
from unittest.mock import MagicMock, patch
import os
import requests
from src.ai_client import GeminiClient, OllamaClient, OpenAIClient, get_ai_client, AIClient

class ConcreteAIClient(AIClient):
    """Helper class to test abstract base class methods"""
    def resolve_conflict(self, f, c): return ""
    def generate_pr_comment(self, i): return ""

class TestAIClient(unittest.TestCase):
    def test_extract_code_block(self):
        client = ConcreteAIClient()
        text = "Some text\n```python\nprint('hello')\n```\nEnd text"
        extracted = client._extract_code_block(text)
        self.assertEqual(extracted, "print('hello')\n")

    def test_extract_code_block_no_block(self):
        client = ConcreteAIClient()
        text = "Just text"
        extracted = client._extract_code_block(text)
        self.assertEqual(extracted, "Just text\n")

    def test_extract_code_block_plain_fences(self):
        client = ConcreteAIClient()
        text = "Some text\n```\nprint('hello')\n```"
        extracted = client._extract_code_block(text)
        self.assertEqual(extracted, "print('hello')\n")

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
    @patch("src.ai_client.ollama.Client")
    def test_resolve_conflict(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_instance.generate.return_value = {"response": "```python\nprint('hello')\n```"}

        client = OllamaClient(base_url="http://mock-url", model="mock-model")
        result = client.resolve_conflict("context", "conflict")

        self.assertEqual(result, "print('hello')\n")
        mock_client_cls.assert_called_with(host="http://mock-url")
        mock_instance.generate.assert_called_with(model="mock-model", prompt=unittest.mock.ANY, stream=False)

    @patch("src.ai_client.ollama.Client")
    def test_resolve_conflict_no_block(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_instance.generate.return_value = {"response": "Just code"}

        client = OllamaClient(base_url="http://mock-url", model="mock-model")
        result = client.resolve_conflict("context", "conflict")
        self.assertEqual(result, "Just code\n")

    @patch("src.ai_client.ollama.Client")
    def test_generate_pr_comment(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_instance.generate.return_value = {"response": "Fix the bugs"}

        client = OllamaClient(base_url="http://mock-url", model="mock-model")
        result = client.generate_pr_comment("pipeline failed")
        self.assertEqual(result, "Fix the bugs")

    @patch("src.ai_client.ollama.Client")
    def test_error_handling(self, mock_client_cls):
        mock_instance = mock_client_cls.return_value
        mock_instance.generate.side_effect = Exception("Connection refused")

        client = OllamaClient(base_url="http://mock-url", model="mock-model")
        with self.assertRaises(Exception):
             client.generate_pr_comment("issue")


class TestOpenAIClient(unittest.TestCase):
    @patch("src.ai_client.requests.post")
    def test_generate_pr_comment(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Please fix CI errors"}}]
        }
        mock_post.return_value = mock_response

        client = OpenAIClient(api_key="openai-key", model="gpt-4o")
        result = client.generate_pr_comment("test issue")

        self.assertEqual(result, "Please fix CI errors")

        # Verify payload structure
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['model'], "gpt-4o")
        self.assertEqual(kwargs['json']['messages'][0]['role'], "user")

    @patch("src.ai_client.requests.post")
    def test_resolve_conflict(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "```python\nprint('ok')\n```"}}]
        }
        mock_post.return_value = mock_response

        client = OpenAIClient(api_key="openai-key", model="gpt-4o")
        result = client.resolve_conflict("context", "conflict")
        self.assertEqual(result, "print('ok')\n")

    @patch("src.ai_client.requests.post")
    def test_empty_response_handling(self, mock_post):
        mock_response = MagicMock()
        # Simulate empty/malformed response
        mock_response.json.return_value = {}
        mock_post.return_value = mock_response

        client = OpenAIClient(api_key="key")
        result = client.generate_pr_comment("issue")
        self.assertEqual(result, "")

    def test_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            client = OpenAIClient()
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
        client = get_ai_client("openai", api_key="openai-key", model="gpt-4o")
        self.assertIsInstance(client, OpenAIClient)
        self.assertEqual(client.model, "gpt-4o")

    def test_unknown_provider(self):
        with self.assertRaises(ValueError):
            get_ai_client("unknown")

if __name__ == '__main__':
    unittest.main()
