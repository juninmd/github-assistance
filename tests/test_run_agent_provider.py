
import unittest
from unittest.mock import MagicMock, patch
import sys
from src.run_agent import main
from src.agents.pr_assistant import PRAssistantAgent
from src.ai_client import GeminiClient, OllamaClient, OpenAICodexClient

class TestRunAgentProvider(unittest.TestCase):
    @patch("src.run_agent.Settings")
    @patch("src.run_agent.RepositoryAllowlist")
    @patch("src.run_agent.JulesClient")
    @patch("src.run_agent.GithubClient")
    @patch("src.run_agent.PRAssistantAgent")
    @patch("src.run_agent.save_results")
    def test_run_agent_provider_gemini(self, mock_save, mock_pr_agent, mock_github, mock_jules, mock_allowlist, mock_settings):
        # Setup settings
        mock_settings.from_env.return_value.ai_provider = "gemini"
        mock_settings.from_env.return_value.ai_model = "gemini-2.5-flash"
        mock_settings.from_env.return_value.gemini_api_key = "test_key"

        # Run with arguments overriding settings
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant', '--provider', 'gemini', '--model', 'gemini-1.5-pro']):
            main()

            # Verify PRAssistantAgent called with correct args
            mock_pr_agent.assert_called_with(
                jules_client=mock_jules.return_value,
                github_client=mock_github.return_value,
                allowlist=mock_allowlist.return_value,
                target_owner=mock_settings.from_env.return_value.github_owner,
                ai_provider='gemini',
                ai_model='gemini-1.5-pro',
                ai_config={'api_key': 'test_key'}
            )

    @patch("src.run_agent.Settings")
    @patch("src.run_agent.RepositoryAllowlist")
    @patch("src.run_agent.JulesClient")
    @patch("src.run_agent.GithubClient")
    @patch("src.run_agent.PRAssistantAgent")
    @patch("src.run_agent.save_results")
    def test_run_agent_provider_ollama(self, mock_save, mock_pr_agent, mock_github, mock_jules, mock_allowlist, mock_settings):
        # Setup settings
        mock_settings.from_env.return_value.ai_provider = "gemini" # Default in settings
        mock_settings.from_env.return_value.ollama_base_url = "http://localhost:11434"

        # Run with arguments for Ollama
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant', '--provider', 'ollama', '--model', 'llama3']):
            main()

            # Verify PRAssistantAgent called with correct args
            mock_pr_agent.assert_called_with(
                jules_client=mock_jules.return_value,
                github_client=mock_github.return_value,
                allowlist=mock_allowlist.return_value,
                target_owner=mock_settings.from_env.return_value.github_owner,
                ai_provider='ollama',
                ai_model='llama3',
                ai_config={'base_url': 'http://localhost:11434'}
            )


    @patch("src.run_agent.Settings")
    @patch("src.run_agent.RepositoryAllowlist")
    @patch("src.run_agent.JulesClient")
    @patch("src.run_agent.GithubClient")
    @patch("src.run_agent.PRAssistantAgent")
    @patch("src.run_agent.save_results")
    def test_run_agent_provider_openai(self, mock_save, mock_pr_agent, mock_github, mock_jules, mock_allowlist, mock_settings):
        # Setup settings
        mock_settings.from_env.return_value.ai_provider = "gemini"
        mock_settings.from_env.return_value.openai_api_key = "openai_test_key"

        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant', '--provider', 'openai', '--model', 'gpt-5-codex']):
            main()

            mock_pr_agent.assert_called_with(
                jules_client=mock_jules.return_value,
                github_client=mock_github.return_value,
                allowlist=mock_allowlist.return_value,
                target_owner=mock_settings.from_env.return_value.github_owner,
                ai_provider='openai',
                ai_model='gpt-5-codex',
                ai_config={'api_key': 'openai_test_key'}
            )

    def test_pr_assistant_init_client(self):
        """Test that PRAssistantAgent correctly initializes the AI client."""
        mock_jules = MagicMock()
        mock_github = MagicMock()
        mock_allowlist = MagicMock()

        # Test Gemini Init
        agent = PRAssistantAgent(
            jules_client=mock_jules,
            github_client=mock_github,
            allowlist=mock_allowlist,
            ai_provider="gemini",
            ai_model="gemini-test",
            ai_config={"api_key": "key"}
        )
        self.assertIsInstance(agent.ai_client, GeminiClient)
        self.assertEqual(agent.ai_client.model, "gemini-test")

        # Test Ollama Init
        agent = PRAssistantAgent(
            jules_client=mock_jules,
            github_client=mock_github,
            allowlist=mock_allowlist,
            ai_provider="ollama",
            ai_model="llama-test",
            ai_config={"base_url": "http://test:1234"}
        )
        self.assertIsInstance(agent.ai_client, OllamaClient)
        self.assertEqual(agent.ai_client.model, "llama-test")
        self.assertEqual(agent.ai_client.base_url, "http://test:1234")

        # Test OpenAI Codex Init
        agent = PRAssistantAgent(
            jules_client=mock_jules,
            github_client=mock_github,
            allowlist=mock_allowlist,
            ai_provider="openai",
            ai_model="gpt-5-codex",
            ai_config={"api_key": "openai-key"}
        )
        self.assertIsInstance(agent.ai_client, OpenAICodexClient)
        self.assertEqual(agent.ai_client.model, "gpt-5-codex")

if __name__ == '__main__':
    unittest.main()
