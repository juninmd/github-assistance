import unittest
from unittest.mock import MagicMock, patch
from src.agents.pr_assistant.agent import PRAssistantAgent
from src.ai_client import GeminiClient, OllamaClient

class TestAgentAIConfig(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()

    def test_init_gemini(self):
        with patch("src.ai_client.GeminiClient") as mock_gemini:
            agent = PRAssistantAgent(
                self.mock_jules,
                self.mock_github,
                self.mock_allowlist,
                ai_provider="gemini",
                ai_model="gemini-pro"
            )
            mock_gemini.assert_called()
            call_args = mock_gemini.call_args[1]
            self.assertEqual(call_args.get('model'), "gemini-pro")

    def test_init_ollama(self):
        with patch("src.ai_client.OllamaClient") as mock_ollama:
            agent = PRAssistantAgent(
                self.mock_jules,
                self.mock_github,
                self.mock_allowlist,
                ai_provider="ollama",
                ai_model="llama2"
            )
            mock_ollama.assert_called()
            call_args = mock_ollama.call_args[1]
            self.assertEqual(call_args.get('model'), "llama2")

    def test_init_default(self):
        with patch("src.ai_client.GeminiClient") as mock_gemini:
            agent = PRAssistantAgent(
                self.mock_jules,
                self.mock_github,
                self.mock_allowlist
            )
            mock_gemini.assert_called()
