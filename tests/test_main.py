import sys
import unittest
from unittest.mock import MagicMock, patch
import os
from src.main import main
from src.run_agent import main as run_agent_main, save_results, ensure_logs_dir

class TestMain(unittest.TestCase):
    @patch('src.main.PRAssistantAgent')
    @patch('src.main.Settings')
    @patch('src.main.GithubClient')
    @patch('src.main.JulesClient')
    @patch('src.main.RepositoryAllowlist')
    def test_main(self, mock_allowlist, mock_jules_client, mock_github_client, mock_settings, mock_pr_agent):
        mock_settings_instance = MagicMock()
        mock_settings_instance.jules_api_key = "test_key"
        mock_settings_instance.github_owner = "test_owner"
        mock_settings_instance.ai_provider = "gemini"
        mock_settings_instance.ai_model = "gemini-flash"
        mock_settings_instance.gemini_api_key = "gemini_key"
        mock_settings.from_env.return_value = mock_settings_instance

        mock_agent_instance = MagicMock()
        mock_pr_agent.return_value = mock_agent_instance
        mock_agent_instance.run.return_value = {"status": "success"}

        main()

        mock_pr_agent.assert_called_once()
        mock_agent_instance.run.assert_called_once()

    @patch('src.main.Settings')
    def test_main_exception(self, mock_settings):
        mock_settings.from_env.side_effect = Exception("Test error")
        with patch('sys.exit') as mock_exit:
            main()
            mock_exit.assert_called_with(1)

class TestRunAgent(unittest.TestCase):
    def setUp(self):
        # Prevent actual file writing
        self.patcher = patch('builtins.open', new_callable=MagicMock)
        self.mock_open = self.patcher.start()

        self.mkdir_patcher = patch('pathlib.Path.mkdir')
        self.mock_mkdir = self.mkdir_patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.mkdir_patcher.stop()

    @patch('src.run_agent.PRAssistantAgent')
    @patch('src.run_agent.Settings')
    @patch('src.run_agent.GithubClient')
    @patch('src.run_agent.JulesClient')
    @patch('src.run_agent.RepositoryAllowlist')
    def test_run_pr_assistant(self, mock_allowlist, mock_jules_client, mock_github_client, mock_settings, mock_pr_agent):
        mock_settings_instance = MagicMock()
        mock_settings_instance.jules_api_key = "test_key"
        mock_settings_instance.github_owner = "test_owner"
        mock_settings_instance.ai_provider = "ollama"
        mock_settings_instance.ai_model = "llama3"
        mock_settings_instance.ollama_base_url = "http://localhost:11434"
        mock_settings.from_env.return_value = mock_settings_instance

        mock_pr_agent.return_value.run.return_value = {"status": "success"}

        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant']):
            run_agent_main()

        mock_pr_agent.assert_called_once()
        _, kwargs = mock_pr_agent.call_args
        self.assertEqual(kwargs['ai_provider'], 'ollama')
        self.assertEqual(kwargs['ai_model'], 'llama3')
        self.assertEqual(kwargs['ai_config']['base_url'], 'http://localhost:11434')

    @patch('src.run_agent.ProductManagerAgent')
    @patch('src.run_agent.Settings')
    @patch('src.run_agent.GithubClient')
    @patch('src.run_agent.JulesClient')
    @patch('src.run_agent.RepositoryAllowlist')
    def test_run_product_manager(self, mock_allowlist, mock_jules_client, mock_github_client, mock_settings, mock_agent):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent.return_value.run.return_value = {"status": "success"}
        with patch.object(sys, 'argv', ['run-agent', 'product-manager']):
            run_agent_main()
        mock_agent.assert_called_once()

    @patch('src.run_agent.InterfaceDeveloperAgent')
    @patch('src.run_agent.Settings')
    @patch('src.run_agent.GithubClient')
    @patch('src.run_agent.JulesClient')
    @patch('src.run_agent.RepositoryAllowlist')
    def test_run_interface_developer(self, mock_allowlist, mock_jules_client, mock_github_client, mock_settings, mock_agent):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent.return_value.run.return_value = {"status": "success"}
        with patch.object(sys, 'argv', ['run-agent', 'interface-developer']):
            run_agent_main()
        mock_agent.assert_called_once()

    @patch('src.run_agent.SeniorDeveloperAgent')
    @patch('src.run_agent.Settings')
    @patch('src.run_agent.GithubClient')
    @patch('src.run_agent.JulesClient')
    @patch('src.run_agent.RepositoryAllowlist')
    def test_run_senior_developer(self, mock_allowlist, mock_jules_client, mock_github_client, mock_settings, mock_agent):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent.return_value.run.return_value = {"status": "success"}
        with patch.object(sys, 'argv', ['run-agent', 'senior-developer']):
            run_agent_main()
        mock_agent.assert_called_once()

    @patch('src.run_agent.SecurityScannerAgent')
    @patch('src.run_agent.Settings')
    @patch('src.run_agent.GithubClient')
    @patch('src.run_agent.JulesClient')
    @patch('src.run_agent.RepositoryAllowlist')
    def test_run_security_scanner(self, mock_allowlist, mock_jules_client, mock_github_client, mock_settings, mock_agent):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent.return_value.run.return_value = {"status": "success"}
        with patch.object(sys, 'argv', ['run-agent', 'security-scanner']):
            run_agent_main()
        mock_agent.assert_called_once()

    @patch('sys.exit')
    def test_run_unknown_agent(self, mock_exit):
        mock_exit.side_effect = SystemExit
        with patch.object(sys, 'argv', ['run-agent', 'unknown']):
            with self.assertRaises(SystemExit):
                run_agent_main()
        mock_exit.assert_called_with(1)

    @patch('sys.exit')
    def test_run_no_args(self, mock_exit):
        mock_exit.side_effect = SystemExit
        with patch.object(sys, 'argv', ['run-agent']):
            with self.assertRaises(SystemExit):
                run_agent_main()
        mock_exit.assert_called_with(1)

    @patch('src.run_agent.PRAssistantAgent')
    @patch('src.run_agent.ProductManagerAgent')
    @patch('src.run_agent.InterfaceDeveloperAgent')
    @patch('src.run_agent.SeniorDeveloperAgent')
    @patch('src.run_agent.SecurityScannerAgent')
    @patch('src.run_agent.Settings')
    @patch('src.run_agent.GithubClient')
    @patch('src.run_agent.JulesClient')
    @patch('src.run_agent.RepositoryAllowlist')
    def test_run_all(self, *args):
        # Setup mocks to return something so it doesn't crash
        for arg in args:
             if hasattr(arg, 'return_value'):
                arg.return_value.run.return_value = {"status": "success"}

        with patch.object(sys, 'argv', ['run-agent', 'all']):
            run_agent_main()

    @patch('src.run_agent.Settings')
    def test_run_exception(self, mock_settings):
        mock_settings.from_env.side_effect = Exception("Test error")
        with patch('sys.exit') as mock_exit:
            mock_exit.side_effect = SystemExit
            with patch.object(sys, 'argv', ['run-agent', 'pr-assistant']):
                 with self.assertRaises(SystemExit):
                    run_agent_main()
            mock_exit.assert_called_with(1)

    def test_save_results(self):
        save_results("test-agent", {"status": "ok"})
        self.mock_open.assert_called_once()
