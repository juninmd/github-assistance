import sys
import unittest
from unittest.mock import MagicMock, patch

from src.run_agent import main as run_agent_main
from src.run_agent import save_results


class TestRunAgent(unittest.TestCase):
    @patch('src.run_agent.send_execution_report')
    @patch('src.run_agent.create_base_deps')
    @patch('src.run_agent.create_agent')
    @patch('src.run_agent.Settings')
    def test_run_pr_assistant(self, mock_settings, mock_create_agent, mock_create_deps, mock_report):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run.return_value = {"status": "success"}
        mock_create_agent.return_value = mock_agent
        mock_create_deps.return_value = {"telegram": MagicMock()}

        with patch.object(sys, "argv", ["run-agent", "pr-assistant"]):
            run_agent_main()

        mock_create_agent.assert_called_once()

    @patch('src.run_agent.send_execution_report')
    @patch('src.run_agent.create_base_deps')
    @patch('src.run_agent.create_agent')
    @patch('src.run_agent.Settings')
    def test_run_product_manager(self, mock_settings, mock_create_agent, mock_create_deps, mock_report):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run.return_value = {"status": "success"}
        mock_create_agent.return_value = mock_agent
        mock_create_deps.return_value = {"telegram": MagicMock()}

        with patch.object(sys, "argv", ["run-agent", "product-manager"]):
            run_agent_main()

        mock_create_agent.assert_called_once()

    @patch("sys.exit")
    def test_run_unknown_agent(self, mock_exit):
        mock_exit.side_effect = SystemExit
        with patch.object(sys, "argv", ["run-agent", "unknown"]):
            with self.assertRaises(SystemExit):
                run_agent_main()
        mock_exit.assert_called_with(2)

    @patch("sys.exit")
    def test_run_no_args(self, mock_exit):
        mock_exit.side_effect = SystemExit
        with patch.object(sys, "argv", ["run-agent"]):
            with self.assertRaises(SystemExit):
                run_agent_main()
        mock_exit.assert_called_with(2)

    @patch('src.run_agent.send_execution_report')
    @patch('src.run_agent.create_base_deps')
    @patch('src.run_agent.run_all')
    @patch('src.run_agent.Settings')
    def test_run_all(self, mock_settings, mock_run_all, mock_create_deps, mock_report):
        mock_settings.from_env.return_value = MagicMock()
        mock_run_all.return_value = {"status": "success"}
        mock_create_deps.return_value = {"telegram": MagicMock()}

        with patch.object(sys, "argv", ["run-agent", "all"]):
            run_agent_main()

        mock_run_all.assert_called_once()

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=MagicMock)
    def test_save_results(self, mock_open, mock_mkdir):
        save_results("test-agent", {"status": "ok"})
        mock_mkdir.assert_called_once()
        mock_open.assert_called_once()
