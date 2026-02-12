import unittest
from unittest.mock import MagicMock, patch
import sys
from src.run_agent import main, run_pr_assistant

class TestRunAgentCoverage(unittest.TestCase):
    @patch("src.run_agent.sys.exit")
    @patch("builtins.print")
    def test_main_no_args(self, mock_print, mock_exit):
        mock_exit.side_effect = SystemExit(1)
        with patch.object(sys, 'argv', ['run-agent']):
            with self.assertRaises(SystemExit):
                main()
            mock_exit.assert_called_with(1)
            mock_print.assert_called()

    @patch("src.run_agent.sys.exit")
    @patch("builtins.print")
    def test_main_unknown_agent(self, mock_print, mock_exit):
        with patch.object(sys, 'argv', ['run-agent', 'unknown']):
            main()
            mock_exit.assert_called_with(1)
            mock_print.assert_any_call("Unknown agent: unknown")

    @patch("src.run_agent.run_product_manager")
    @patch("src.run_agent.run_interface_developer")
    @patch("src.run_agent.run_senior_developer")
    @patch("src.run_agent.run_pr_assistant")
    @patch("src.run_agent.run_security_scanner")
    @patch("src.run_agent.save_results")
    def test_main_all_agents(self, mock_save, mock_sec, mock_pr, mock_sen, mock_int, mock_prod):
        with patch.object(sys, 'argv', ['run-agent', 'all']):
            main()
            mock_prod.assert_called()
            mock_int.assert_called()
            mock_sen.assert_called()
            mock_pr.assert_called()
            mock_sec.assert_called()
            mock_save.assert_called()

    @patch("src.run_agent.run_product_manager")
    @patch("src.run_agent.save_results")
    def test_main_all_agents_exception(self, mock_save, mock_prod):
        mock_prod.side_effect = Exception("Run Error")
        with patch.object(sys, 'argv', ['run-agent', 'all']):
            main()
            mock_prod.assert_called()
            # check that save_results was called with error
            args = mock_save.call_args[0]
            self.assertEqual(args[0], "all-agents")
            self.assertIn("error", args[1]["product-manager"])

    @patch("src.run_agent.run_pr_assistant")
    def test_main_specific_agent(self, mock_pr):
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant']):
            main()
            mock_pr.assert_called()

    @patch("src.run_agent.run_pr_assistant")
    @patch("src.run_agent.sys.exit")
    def test_main_agent_exception(self, mock_exit, mock_pr):
        mock_pr.side_effect = Exception("Fatal")
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant']):
            main()
            mock_exit.assert_called_with(1)

    @patch("src.run_agent.Settings")
    @patch("src.run_agent.PRAssistantAgent")
    @patch("src.run_agent.save_results")
    @patch("src.run_agent.JulesClient")
    @patch("src.run_agent.GithubClient")
    @patch("src.run_agent.RepositoryAllowlist")
    def test_run_pr_assistant_config_gemini(self, mock_allow, mock_gh, mock_jules, mock_save, mock_agent_cls, mock_settings_cls):
        mock_settings = MagicMock()
        mock_settings.ai_provider = "gemini"
        mock_settings.gemini_api_key = "key"
        mock_settings.ai_model = "model"
        mock_settings.github_owner = "owner"
        mock_settings_cls.from_env.return_value = mock_settings

        run_pr_assistant()

        mock_agent_cls.assert_called()
        _, kwargs = mock_agent_cls.call_args
        self.assertEqual(kwargs['ai_provider'], 'gemini')
        self.assertEqual(kwargs['ai_config']['api_key'], 'key')

    @patch("src.run_agent.Settings")
    @patch("src.run_agent.PRAssistantAgent")
    @patch("src.run_agent.save_results")
    @patch("src.run_agent.JulesClient")
    @patch("src.run_agent.GithubClient")
    @patch("src.run_agent.RepositoryAllowlist")
    def test_run_pr_assistant_config_ollama(self, mock_allow, mock_gh, mock_jules, mock_save, mock_agent_cls, mock_settings_cls):
        mock_settings = MagicMock()
        mock_settings.ai_provider = "ollama"
        mock_settings.ollama_base_url = "http://url"
        mock_settings.ai_model = "model"
        mock_settings_cls.from_env.return_value = mock_settings

        run_pr_assistant()

        mock_agent_cls.assert_called()
        _, kwargs = mock_agent_cls.call_args
        self.assertEqual(kwargs['ai_provider'], 'ollama')
        self.assertEqual(kwargs['ai_config']['base_url'], 'http://url')

if __name__ == '__main__':
    unittest.main()
