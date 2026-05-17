import sys
import unittest
from unittest.mock import MagicMock, patch

from src.config.settings import Settings
from src.main import main
from src.run_agent import main as run_agent_main
from src.run_agent import save_results


class TestMain(unittest.TestCase):
    @patch('src.main.PRAssistantAgent')
    @patch('src.main.Settings')
    @patch('src.main.GithubClient')
    @patch('src.main.JulesClient')
    @patch('src.main.RepositoryAllowlist')
    def test_main_default(self, mock_allowlist, mock_jules_client, mock_github_client, mock_settings, mock_pr_agent):
        mock_settings_instance = MagicMock()
        mock_settings_instance.jules_api_key = "test_key"
        mock_settings_instance.github_owner = "test_owner"
        mock_settings_instance.ai_provider = Settings.ai_provider
        mock_settings_instance.ai_model = Settings.ai_model
        mock_settings_instance.gemini_api_key = "gemini_key"
        mock_settings.from_env.return_value = mock_settings_instance

        mock_agent_instance = MagicMock()
        mock_pr_agent.return_value = mock_agent_instance
        mock_agent_instance.run.return_value = {"status": "success"}

        with patch.object(sys, 'argv', ['pr-assistant']):
            main()

        mock_pr_agent.assert_called_once()
        _, kwargs = mock_pr_agent.call_args
        self.assertEqual(kwargs['ai_provider'], Settings.ai_provider)
        self.assertEqual(kwargs['ai_model'], Settings.ai_model)

        mock_agent_instance.run.assert_called_once()

    @patch('src.main.PRAssistantAgent')
    @patch('src.main.Settings')
    @patch('src.main.GithubClient')
    @patch('src.main.JulesClient')
    @patch('src.main.RepositoryAllowlist')
    def test_main_with_args(self, mock_allowlist, mock_jules_client, mock_github_client, mock_settings, mock_pr_agent):
        mock_settings_instance = MagicMock()
        mock_settings_instance.jules_api_key = "test_key"
        mock_settings_instance.github_owner = "test_owner"
        mock_settings_instance.ai_provider = "gemini"
        mock_settings_instance.ai_model = "gemini-flash"
        mock_settings_instance.ollama_base_url = "http://localhost:11434"
        mock_settings.from_env.return_value = mock_settings_instance

        mock_agent_instance = MagicMock()
        mock_pr_agent.return_value = mock_agent_instance
        mock_agent_instance.run.return_value = {"status": "success"}

        with patch.object(sys, 'argv', ['pr-assistant', 'owner/repo#123', '--provider', 'ollama', '--model', 'llama3']):
            main()

        mock_pr_agent.assert_called_once()
        _, kwargs = mock_pr_agent.call_args
        self.assertEqual(kwargs['ai_provider'], 'ollama')
        self.assertEqual(kwargs['ai_model'], 'llama3')
        self.assertEqual(kwargs['ai_config']['base_url'], 'http://localhost:11434')

        mock_agent_instance.run.assert_called_once()

    @patch('src.main.PRAssistantAgent')
    @patch('src.main.Settings')
    @patch('src.main.GithubClient')
    @patch('src.main.JulesClient')
    @patch('src.main.RepositoryAllowlist')
    def test_main_with_provider_no_model(self, mock_allowlist, mock_jules_client, mock_github_client, mock_settings, mock_pr_agent):
        mock_settings_instance = MagicMock()
        mock_settings_instance.jules_api_key = "test_key"
        mock_settings_instance.github_owner = "test_owner"
        mock_settings_instance.ai_provider = "gemini"
        mock_settings_instance.ai_model = "gemini-flash"
        mock_settings_instance.ollama_base_url = "http://localhost:11434"
        mock_settings.from_env.return_value = mock_settings_instance

        mock_agent_instance = MagicMock()
        mock_pr_agent.return_value = mock_agent_instance
        mock_agent_instance.run.return_value = {"status": "success"}

        with patch.object(sys, 'argv', ['pr-assistant', 'owner/repo#123', '--provider', 'ollama']):
            main()

        mock_pr_agent.assert_called_once()
        _, kwargs = mock_pr_agent.call_args
        self.assertEqual(kwargs['ai_provider'], 'ollama')
        self.assertEqual(kwargs['ai_model'], 'qwen3:1.7b')

    @patch('src.main.PRAssistantAgent')
    @patch('src.main.Settings')
    @patch('src.main.GithubClient')
    @patch('src.main.JulesClient')
    @patch('src.main.RepositoryAllowlist')
    def test_main_with_provider_openai(self, mock_allowlist, mock_jules_client, mock_github_client, mock_settings, mock_pr_agent):
        mock_settings_instance = MagicMock()
        mock_settings_instance.jules_api_key = "test_key"
        mock_settings_instance.github_owner = "test_owner"
        mock_settings_instance.ai_provider = "gemini"
        mock_settings_instance.ai_model = "gemini-flash"
        mock_settings_instance.openai_api_key = "sk-..."
        mock_settings.from_env.return_value = mock_settings_instance

        mock_agent_instance = MagicMock()
        mock_pr_agent.return_value = mock_agent_instance
        mock_agent_instance.run.return_value = {"status": "success"}

        with patch.object(sys, 'argv', ['pr-assistant', 'owner/repo#123', '--provider', 'openai']):
            main()

        mock_pr_agent.assert_called_once()
        _, kwargs = mock_pr_agent.call_args
        self.assertEqual(kwargs['ai_provider'], 'openai')
        self.assertEqual(kwargs['ai_model'], 'gpt-4o')


    @patch('src.main.Settings')
    def test_main_exception(self, mock_settings):
        mock_settings.from_env.side_effect = Exception("Test error")
        with patch('sys.exit') as mock_exit:
            with patch.object(sys, 'argv', ['pr-assistant']):
                main()
            mock_exit.assert_called_with(1)

class TestRunAgent(unittest.TestCase):
    @patch('src.run_agent.send_execution_report')
    @patch('src.run_agent._create_base_deps')
    @patch('src.run_agent._create_agent')
    @patch('src.run_agent.Settings')
    def test_run_pr_assistant(self, mock_settings, mock_create_agent, mock_create_deps, mock_report):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run.return_value = {"status": "success"}
        mock_create_agent.return_value = mock_agent
        mock_create_deps.return_value = {"telegram": MagicMock()}

        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant']):
            run_agent_main()

        mock_create_agent.assert_called_once()

    @patch('src.run_agent.send_execution_report')
    @patch('src.run_agent._create_base_deps')
    @patch('src.run_agent._create_agent')
    @patch('src.run_agent.Settings')
    def test_run_product_manager(self, mock_settings, mock_create_agent, mock_create_deps, mock_report):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run.return_value = {"status": "success"}
        mock_create_agent.return_value = mock_agent
        mock_create_deps.return_value = {"telegram": MagicMock()}

        with patch.object(sys, 'argv', ['run-agent', 'product-manager']):
            run_agent_main()

        mock_create_agent.assert_called_once()

    @patch('sys.exit')
    def test_run_unknown_agent(self, mock_exit):
        mock_exit.side_effect = SystemExit
        with patch.object(sys, 'argv', ['run-agent', 'unknown']):
            with self.assertRaises(SystemExit):
                run_agent_main()
        mock_exit.assert_called_with(2)

    @patch('sys.exit')
    def test_run_no_args(self, mock_exit):
        mock_exit.side_effect = SystemExit
        with patch.object(sys, 'argv', ['run-agent']):
            with self.assertRaises(SystemExit):
                run_agent_main()
        mock_exit.assert_called_with(2)

    @patch('src.run_agent.send_execution_report')
    @patch('src.run_agent._create_base_deps')
    @patch('src.run_agent.run_all')
    @patch('src.run_agent.Settings')
    def test_run_all(self, mock_settings, mock_run_all, mock_create_deps, mock_report):
        mock_settings.from_env.return_value = MagicMock()
        mock_run_all.return_value = {"status": "success"}
        mock_create_deps.return_value = {"telegram": MagicMock()}

        with patch.object(sys, 'argv', ['run-agent', 'all']):
            run_agent_main()

        mock_run_all.assert_called_once()

    @patch('pathlib.Path.mkdir')
    @patch('builtins.open', new_callable=MagicMock)
    def test_save_results(self, mock_open, mock_mkdir):
        save_results("test-agent", {"status": "ok"})
        mock_mkdir.assert_called_once()
        mock_open.assert_called_once()