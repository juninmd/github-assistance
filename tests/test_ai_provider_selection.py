import unittest
from unittest.mock import MagicMock, patch
from src.agents.pr_assistant.agent import PRAssistantAgent
from src.ai_client import GeminiClient, OllamaClient

class TestAIProviderSelection(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True

    @patch("src.agents.pr_assistant.agent.get_ai_client")
    def test_default_provider_gemini(self, mock_get_ai_client):
        """Test that default provider is Gemini with default model."""
        agent = PRAssistantAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            target_owner="juninmd"
        )

        # Verify get_ai_client called with default 'gemini' and default model
        mock_get_ai_client.assert_called_once()
        args, kwargs = mock_get_ai_client.call_args
        self.assertEqual(args[0], "gemini")
        self.assertEqual(kwargs["model"], "gemini-2.5-flash")

    @patch("src.agents.pr_assistant.agent.get_ai_client")
    def test_provider_ollama(self, mock_get_ai_client):
        """Test choosing Ollama provider."""
        ai_config = {"base_url": "http://ollama:11434"}
        agent = PRAssistantAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            target_owner="juninmd",
            ai_provider="ollama",
            ai_model="llama3",
            ai_config=ai_config
        )

        mock_get_ai_client.assert_called_once()
        args, kwargs = mock_get_ai_client.call_args
        self.assertEqual(args[0], "ollama")
        self.assertEqual(kwargs["model"], "llama3")
        self.assertEqual(kwargs["base_url"], "http://ollama:11434")

    @patch("src.agents.pr_assistant.agent.get_ai_client")
    def test_custom_gemini_model(self, mock_get_ai_client):
        """Test choosing Gemini with custom model."""
        agent = PRAssistantAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            target_owner="juninmd",
            ai_provider="gemini",
            ai_model="gemini-1.5-pro"
        )

        mock_get_ai_client.assert_called_once()
        args, kwargs = mock_get_ai_client.call_args
        self.assertEqual(args[0], "gemini")
        self.assertEqual(kwargs["model"], "gemini-1.5-pro")

    def test_real_gemini_client_initialization(self):
        """Test real GeminiClient initialization via factory (mocking internal client)."""
        with patch("src.ai_client.genai.Client"):
            with patch("os.environ.get", return_value="fake_key"):
                 agent = PRAssistantAgent(
                    self.mock_jules,
                    self.mock_github,
                    self.mock_allowlist,
                    target_owner="juninmd",
                    ai_provider="gemini",
                    ai_model="gemini-pro"
                )
                 self.assertIsInstance(agent.ai_client, GeminiClient)
                 self.assertEqual(agent.ai_client.model, "gemini-pro")

    def test_real_ollama_client_initialization(self):
        """Test real OllamaClient initialization via factory."""
        agent = PRAssistantAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            target_owner="juninmd",
            ai_provider="ollama",
            ai_model="mistral"
        )
        self.assertIsInstance(agent.ai_client, OllamaClient)
        self.assertEqual(agent.ai_client.model, "mistral")

if __name__ == '__main__':
    unittest.main()
