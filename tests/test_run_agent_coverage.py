import sys
import unittest
from unittest.mock import MagicMock, patch

from src.notifications.telegram import TelegramNotifier
from src.run_agent import (  # pyright: ignore[reportUnusedImport]
    main,
    save_results,
    send_execution_report,
)


class TestRunAgentCoverage(unittest.TestCase):
    @patch("sys.exit")
    def test_main_no_args(self, mock_exit):
        mock_exit.side_effect = SystemExit(2)
        with patch.object(sys, 'argv', ['run-agent']):
            with self.assertRaises(SystemExit):
                main()
            mock_exit.assert_called_with(2)

    @patch("sys.exit")
    def test_main_unknown_agent(self, mock_exit):
        mock_exit.side_effect = SystemExit(2)
        with patch.object(sys, 'argv', ['run-agent', 'unknown']):
            with self.assertRaises(SystemExit):
                main()
            mock_exit.assert_called_with(2)

    @patch("src.run_agent.send_execution_report")
    @patch("src.run_agent._create_base_deps")
    @patch("src.run_agent.run_all")
    @patch("src.run_agent.Settings")
    def test_main_all_agents(self, mock_settings, mock_run_all, mock_deps, mock_report):
        mock_settings.from_env.return_value = MagicMock()
        mock_run_all.return_value = {"status": "ok"}
        mock_deps.return_value = {"telegram": MagicMock()}
        with patch.object(sys, 'argv', ['run-agent', 'all']):
            main()
        mock_run_all.assert_called_once()

    @patch("src.run_agent.send_execution_report")
    @patch("src.run_agent._create_base_deps")
    @patch("src.run_agent._create_agent")
    @patch("src.run_agent.Settings")
    def test_main_specific_agent(self, mock_settings, mock_create, mock_deps, mock_report):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run.return_value = {"status": "success"}
        mock_create.return_value = mock_agent
        mock_deps.return_value = {"telegram": MagicMock()}
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant']):
            main()
        mock_create.assert_called_once()

    @patch("src.run_agent.send_execution_report")
    @patch("src.run_agent._create_base_deps")
    @patch("src.run_agent._create_agent")
    @patch("src.run_agent.Settings")
    def test_main_agent_exception(self, mock_settings, mock_create, mock_deps, mock_report):
        mock_settings.from_env.return_value = MagicMock()
        mock_create.side_effect = Exception("Fatal")
        mock_deps.return_value = {"telegram": MagicMock()}
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant']):
            with self.assertRaises(Exception):
                main()

    @patch("os.makedirs")
    @patch("builtins.open", new_callable=MagicMock)
    def test_save_results(self, mock_open, mock_makedirs):
        save_results("test-agent", {"status": "ok"})
        mock_makedirs.assert_called_once()
        mock_open.assert_called_once()

    def test_send_execution_report(self):
        telegram = MagicMock(spec=TelegramNotifier)
        telegram.escape = TelegramNotifier.escape
        send_execution_report(telegram, "test-agent", {"merged": [1, 2], "failed": []})
        telegram.send_message.assert_called_once()

    def test_send_execution_report_with_failures(self):
        telegram = MagicMock(spec=TelegramNotifier)
        telegram.escape = TelegramNotifier.escape
        send_execution_report(telegram, "test-agent", {"processed": [], "failed": [{"error": "x"}]})
        telegram.send_message.assert_called_once()
