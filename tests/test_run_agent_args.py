import sys
import unittest
from unittest.mock import MagicMock, patch

from src.run_agent import main


class TestRunAgentArgs(unittest.TestCase):
    @patch("src.run_agent.run_pr_assistant")
    @patch("src.run_agent.sys.exit")
    def test_pr_assistant_args(self, mock_exit, mock_runner):
        # Test full arguments
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant', 'owner/repo#123', '--provider', 'ollama', '--model', 'llama3']):
            main()
            mock_runner.assert_called_with(pr_ref='owner/repo#123', ai_provider='ollama', ai_model='llama3')

        # Test defaults (no pr_ref, no provider/model)
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant']):
            main()
            mock_runner.assert_called_with(pr_ref=None, ai_provider=None, ai_model=None)

        # Test partial args
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant', '--provider', 'gemini']):
            main()
            mock_runner.assert_called_with(pr_ref=None, ai_provider='gemini', ai_model=None)

    @patch("src.run_agent.run_product_manager")
    @patch("src.run_agent.sys.exit")
    def test_other_agent_args_ignored(self, mock_exit, mock_runner):
        # Even if we pass provider/model, other agents don't receive them currently
        # But argparse accepts them.
        with patch.object(sys, 'argv', ['run-agent', 'product-manager', '--provider', 'ollama']):
            main()
            mock_runner.assert_called_with()

    @patch("src.run_agent.run_pr_assistant")
    @patch("src.run_agent.sys.exit")
    def test_all_agents_pr_assistant_config(self, mock_exit, mock_runner):
        # In 'all' mode, pr-assistant should get the config
        with patch.object(sys, 'argv', ['run-agent', 'all', '--provider', 'ollama', '--model', 'llama3']):
            with patch("src.run_agent.run_product_manager") as mock_pm:
                with patch("src.run_agent.save_results"):
                     main()
                     mock_runner.assert_called_with(ai_provider='ollama', ai_model='llama3')
                     mock_pm.assert_called_with()

if __name__ == '__main__':
    unittest.main()
