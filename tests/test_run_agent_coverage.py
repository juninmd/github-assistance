import sys
import unittest
from unittest.mock import MagicMock, patch

from src.notifications.telegram import TelegramNotifier
from src.run_agent import main, save_results, send_execution_report


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
    def test_main_specific_agent_with_args(self, mock_settings, mock_create, mock_deps, mock_report):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run.return_value = {"status": "success"}
        mock_create.return_value = mock_agent
        mock_deps.return_value = {"telegram": MagicMock()}
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant', '--ai-provider', 'ollama', '--ai-model', 'llama3']):
            main()
        mock_create.assert_called_once()

    @patch("src.run_agent.send_execution_report")
    @patch("src.run_agent._create_base_deps")
    @patch("src.run_agent._create_agent")
    @patch("src.run_agent.Settings")
    def test_main_specific_agent_with_provider_only(self, mock_settings, mock_create, mock_deps, mock_report):
        mock_settings_instance = MagicMock()
        mock_settings_instance.ai_provider = "gemini"
        mock_settings_instance.ai_model = "gemini-2.5-flash"
        mock_settings.from_env.return_value = mock_settings_instance

        mock_agent = MagicMock()
        mock_agent.run.return_value = {"status": "success"}
        mock_create.return_value = mock_agent
        mock_deps.return_value = {"telegram": MagicMock()}
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant', '--ai-provider', 'ollama']):
            main()
        mock_create.assert_called_once()

    @patch("src.run_agent.send_execution_report")
    @patch("src.run_agent._create_base_deps")
    @patch("src.run_agent._create_agent")
    @patch("src.run_agent.Settings")
    def test_main_specific_agent_with_openai_provider_only(self, mock_settings, mock_create, mock_deps, mock_report):
        mock_settings_instance = MagicMock()
        mock_settings_instance.ai_provider = "gemini"
        mock_settings_instance.ai_model = "gemini-2.5-flash"
        mock_settings.from_env.return_value = mock_settings_instance

        mock_agent = MagicMock()
        mock_agent.run.return_value = {"status": "success"}
        mock_create.return_value = mock_agent
        mock_deps.return_value = {"telegram": MagicMock()}
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant', '--ai-provider', 'openai']):
            main()
        mock_create.assert_called_once()

    @patch("src.run_agent.send_execution_report")
    @patch("src.run_agent._create_base_deps")
    @patch("src.run_agent.run_all")
    @patch("src.run_agent.Settings")
    def test_main_all_agents_with_args(self, mock_settings, mock_run_all, mock_deps, mock_report):
        mock_settings_instance = MagicMock()
        mock_settings_instance.enable_ai = True
        mock_settings.from_env.return_value = mock_settings_instance
        mock_run_all.return_value = {"status": "ok"}
        mock_deps.return_value = {"telegram": MagicMock()}
        with patch.object(sys, 'argv', ['run-agent', 'all', '--ai-provider', 'openai']):
            main()
        mock_run_all.assert_called_once()

    @patch("src.run_agent.run_agent")
    def test_run_all_skips_disabled_agents(self, mock_run_agent):
        settings = MagicMock()
        settings.enable_product_manager = False
        settings.enable_interface_developer = False
        settings.enable_senior_developer = False
        settings.enable_pr_assistant = False
        settings.enable_security_scanner = False
        settings.enable_ci_health = False
        settings.enable_release_watcher = False
        settings.enable_dependency_risk = False
        settings.enable_pr_sla = False
        settings.enable_issue_escalation = False
        settings.enable_jules_tracker = False
        settings.enable_secret_remover = False
        settings.enable_project_creator = False
        settings.enable_ai = True

        from src.run_agent import run_all
        run_all(settings)
        self.assertEqual(mock_run_agent.call_count, 2)

    @patch("src.run_agent.run_agent")
    def test_run_all_skips_ai_agents_if_ai_disabled(self, mock_run_agent):
        settings = MagicMock()
        settings.enable_product_manager = True
        settings.enable_interface_developer = True
        settings.enable_senior_developer = True
        settings.enable_pr_assistant = True
        settings.enable_security_scanner = False
        settings.enable_ci_health = False
        settings.enable_release_watcher = False
        settings.enable_dependency_risk = False
        settings.enable_pr_sla = False
        settings.enable_issue_escalation = False
        settings.enable_jules_tracker = True
        settings.enable_secret_remover = True
        settings.enable_ai = False

        from src.run_agent import run_all
        run_all(settings)
        mock_run_agent.assert_not_called()

    @patch("src.run_agent.run_agent")
    def test_run_all_catches_agent_exception(self, mock_run_agent):
        settings = MagicMock()
        settings.enable_product_manager = True
        settings.enable_interface_developer = False
        settings.enable_senior_developer = False
        settings.enable_pr_assistant = False
        settings.enable_security_scanner = False
        settings.enable_ci_health = False
        settings.enable_release_watcher = False
        settings.enable_dependency_risk = False
        settings.enable_pr_sla = False
        settings.enable_issue_escalation = False
        settings.enable_jules_tracker = False
        settings.enable_secret_remover = False
        settings.enable_ai = True

        mock_run_agent.side_effect = Exception("Test error")
        from src.run_agent import run_all
        results = run_all(settings)

        self.assertIn("product-manager", results)
        self.assertIn("error", results["product-manager"])

    def test_create_agent_ai_disabled_error(self):
        settings = MagicMock()
        settings.enable_ai = False
        settings.github_owner = "test"

        from src.run_agent import _create_agent
        with patch("src.run_agent._create_base_deps") as mock_deps:
            mock_deps.return_value = {
                "github_client": MagicMock(),
                "jules_client": MagicMock(),
                "allowlist": MagicMock(),
                "telegram": MagicMock()
            }
            with self.assertRaises(PermissionError):
                _create_agent("pr-assistant", settings)

    def test_create_base_deps(self):
        settings = MagicMock()
        settings.github_token = "token"
        settings.jules_api_key = "key"
        settings.repository_allowlist_path = "path"
        settings.telegram_bot_token = "bot"
        settings.telegram_chat_id = "chat"

        from src.run_agent import _create_base_deps
        with patch("src.run_agent.GithubClient") as mock_gh, \
             patch("src.run_agent.JulesClient") as mock_jc, \
             patch("src.run_agent.RepositoryAllowlist") as mock_ra, \
             patch("src.run_agent.TelegramNotifier") as mock_tn:

            deps = _create_base_deps(settings)

            self.assertIn("github_client", deps)
            self.assertIn("jules_client", deps)
            self.assertIn("allowlist", deps)
            self.assertIn("telegram", deps)
            mock_gh.assert_called_once_with("token")
            mock_jc.assert_called_once_with("key")
            mock_ra.assert_called_once_with("path")
            mock_tn.assert_called_once_with(bot_token="bot", chat_id="chat")

    def test_build_ai_config(self):
        settings = MagicMock()
        settings.ai_provider = "ollama"
        settings.ai_model = "qwen3:1.7b"
        settings.ollama_base_url = "http://localhost:11434"
        settings.gemini_api_key = "gemini-key"
        settings.openai_api_key = "openai-key"

        from src.run_agent import _build_ai_config

        # Test ollama from settings
        config = _build_ai_config(settings)
        self.assertEqual(config["ai_provider"], "ollama")
        self.assertEqual(config["ai_model"], "qwen3:1.7b")
        self.assertEqual(config["ai_config"]["base_url"], "http://localhost:11434")

        # Test gemini override
        config = _build_ai_config(settings, provider="gemini", model="gemini-flash")
        self.assertEqual(config["ai_provider"], "gemini")
        self.assertEqual(config["ai_model"], "gemini-flash")
        self.assertEqual(config["ai_config"]["api_key"], "gemini-key")

        # Test openai override
        config = _build_ai_config(settings, provider="openai", model="gpt-4")
        self.assertEqual(config["ai_provider"], "openai")
        self.assertEqual(config["ai_model"], "gpt-4")
        self.assertEqual(config["ai_config"]["api_key"], "openai-key")

        # Test default model fallback
        config = _build_ai_config(settings, provider="openai")
        self.assertEqual(config["ai_provider"], "openai")
        self.assertEqual(config["ai_model"], "gpt-4o")

    def test_create_agent_with_pr_ref(self):
        settings = MagicMock()
        settings.enable_ai = True
        settings.github_owner = "test"

        from src.run_agent import _create_agent
        with patch("src.run_agent._create_base_deps") as mock_deps, \
             patch("src.run_agent._build_ai_config") as mock_config, \
             patch("src.run_agent.AGENT_REGISTRY") as mock_registry:

            mock_deps.return_value = {
                "github_client": MagicMock(),
                "jules_client": MagicMock(),
                "allowlist": MagicMock(),
                "telegram": MagicMock()
            }
            mock_config.return_value = {"ai_provider": "test", "ai_model": "test", "ai_config": {}}

            mock_agent_cls = MagicMock()
            mock_registry.__getitem__.return_value = mock_agent_cls

            _create_agent("pr-assistant", settings, pr_ref="owner/repo#123")

            # Extract arguments used to instantiate agent class
            kwargs = mock_agent_cls.call_args[1]
            self.assertEqual(kwargs["pr_ref"], "owner/repo#123")

    @patch("src.run_agent.send_execution_report")
    @patch("src.run_agent._create_base_deps")
    @patch("src.run_agent._create_agent")
    @patch("src.run_agent.Settings")
    def test_main_agent_exception(self, mock_settings, mock_create, mock_deps, mock_report):
        mock_settings.from_env.return_value = MagicMock()
        mock_create.side_effect = Exception("Fatal")
        mock_deps.return_value = {"telegram": MagicMock()}
        with patch.object(sys, 'argv', ['run-agent', 'pr-assistant']):
            with self.assertRaises(SystemExit):
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

    def test_send_execution_report_all(self):
        from src.run_agent import send_execution_report
        telegram = MagicMock()
        telegram.escape = lambda x: x
        results = {
            "agent1": {"status": "ok"},
            "agent2": {"error": "failed_run"}
        }
        send_execution_report(telegram, "all", results)
        telegram.send_message.assert_called_once()
        msg = telegram.send_message.call_args[0][0]
        self.assertIn("✅ `agent1`", msg)
        self.assertIn("❌ `agent2`", msg)
        self.assertIn("Error: `failed_run`", msg)

    def test_send_execution_report_single_error(self):
        from src.run_agent import send_execution_report
        telegram = MagicMock()
        telegram.escape = lambda x: x
        results = {"error": "critical_error"}
        send_execution_report(telegram, "pr-assistant", results)
        telegram.send_message.assert_called_once()
        msg = telegram.send_message.call_args[0][0]
        self.assertIn("❌ Status: *Falha Crítica*", msg)
        self.assertIn("Erro: `critical_error`", msg)
