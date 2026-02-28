import sys
import unittest
from unittest.mock import MagicMock, patch

from src.main import main as legacy_main
from src.run_agent import main as run_agent_main


class TestCLICoverage(unittest.TestCase):
    def test_legacy_main_pr_assistant_disabled(self):
        with patch("src.main.Settings.from_env") as mock_settings:
            with patch("src.main.GithubClient"):
                with patch("src.main.JulesClient"):
                    with patch("src.main.RepositoryAllowlist"):
                        # Configure settings
                        mock_settings.return_value.pr_assistant_enabled = False
                        mock_settings.return_value.ai_provider = "gemini"
                        mock_settings.return_value.ai_model = "gemini-pro"
                        mock_settings.return_value.ollama_base_url = "http://localhost:11434"
                        mock_settings.return_value.gemini_api_key = "key"
                        mock_settings.return_value.repository_allowlist_path = "config.json"

                        # Verify it returns early
                        with patch("sys.argv", ["pr-assistant"]):
                            legacy_main()

    def test_run_agent_pr_assistant_with_args(self):
        with patch("sys.argv", ["run-agent", "pr-assistant", "123"]):
            with patch("src.run_agent.run_pr_assistant") as mock_run:
                run_agent_main()
                mock_run.assert_called_once_with(pr_ref="123", ai_provider=None, ai_model=None)

    def test_run_agent_unknown_agent(self):
        with patch("sys.argv", ["run-agent", "unknown"]):
            with patch("sys.exit") as mock_exit:
                run_agent_main()
                mock_exit.assert_called_with(1)

    def test_run_agent_all_exception(self):
        with patch("sys.argv", ["run-agent", "all"]):
            # Mock individual runners
            with patch("src.run_agent.run_product_manager", side_effect=Exception("Fail")):
                with patch("src.run_agent.run_interface_developer"):
                    with patch("src.run_agent.run_senior_developer"):
                        with patch("src.run_agent.run_pr_assistant"):
                            with patch("src.run_agent.run_security_scanner"):
                                with patch("src.run_agent.save_results"):
                                    # Should not crash
                                    run_agent_main()

if __name__ == '__main__':
    unittest.main()
