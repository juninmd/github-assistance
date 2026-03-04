import unittest
from unittest.mock import MagicMock, patch

import src.run_agent


class TestRunAgentGaps(unittest.TestCase):
    @patch("src.run_agent.argparse.ArgumentParser.parse_args")
    @patch("src.run_agent.run_product_manager")
    @patch("src.run_agent.sys.exit")
    def test_main_exception(self, mock_exit, mock_run, mock_args):
        mock_args.return_value.agent_name = "product-manager"
        mock_args.return_value.pr_ref = None
        mock_args.return_value.provider = None
        mock_args.return_value.model = None
        mock_run.side_effect = Exception("test error")

        with patch("src.run_agent.send_execution_report"):
            src.run_agent.main()
            mock_exit.assert_called_with(1)

    @patch("src.run_agent.argparse.ArgumentParser.parse_args")
    @patch("src.run_agent.send_execution_report")
    @patch("src.run_agent.sys.exit")
    def test_main_pr_assistant_args(self, mock_exit, mock_report, mock_args):
        mock_args.return_value.agent_name = "pr-assistant"
        mock_args.return_value.pr_ref = "123"
        mock_args.return_value.provider = "gemini"
        mock_args.return_value.model = "model"

        with patch("src.run_agent.run_pr_assistant") as mock_run:
            mock_run.return_value = {}
            src.run_agent.main()
            mock_run.assert_called_with(pr_ref="123", ai_provider="gemini", ai_model="model")

    @patch("src.run_agent.argparse.ArgumentParser.parse_args")
    @patch("src.run_agent.send_execution_report")
    @patch("src.run_agent.sys.exit")
    def test_main_senior_developer_args(self, mock_exit, mock_report, mock_args):
        mock_args.return_value.agent_name = "senior-developer"
        mock_args.return_value.pr_ref = None
        mock_args.return_value.provider = "gemini"
        mock_args.return_value.model = "model"

        with patch("src.run_agent.run_senior_developer") as mock_run:
            mock_run.return_value = {}
            src.run_agent.main()
            mock_run.assert_called_with(ai_provider="gemini", ai_model="model")


    @patch("src.run_agent.GithubClient")
    def test_send_execution_report_truncate(self, mock_client):
        # test line 63
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        results = {"data": "a" * 1500}
        src.run_agent.send_execution_report("agent", results)

        args = mock_instance._escape_markdown.call_args_list
        # verify truncation ...
        self.assertTrue(any("..." in str(call) for call in args))
