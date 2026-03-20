import os
import unittest
from unittest.mock import MagicMock, patch

from src.ai_client import GeminiClient, OllamaClient, OpenAIClient


class TestAIClientsCoverage(unittest.TestCase):
    @patch("src.ai_client.requests.post")
    def test_openai_client_key_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            client = OpenAIClient()
            res = client.generate("test prompt")
            self.assertEqual(res, "")
