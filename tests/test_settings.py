import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config.settings import Settings

_NO_DOTENV = patch("src.config.settings.load_dotenv")


class TestSettings(unittest.TestCase):
    def test_from_env_defaults(self):
        with (
            _NO_DOTENV,
            patch.dict(os.environ, {"GITHUB_TOKEN": "token", "JULES_API_KEY": "key"}, clear=True),
        ):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_provider, "litellm")
            self.assertEqual(settings.ai_model, "cloud/auto")
            self.assertEqual(settings.ollama_base_url, "http://localhost:11434")
            self.assertIsNone(settings.openai_api_key)

    def test_from_env_custom(self):
        with (
            _NO_DOTENV,
            patch.dict(
                os.environ,
                {
                    "GITHUB_TOKEN": "token",
                    "JULES_API_KEY": "key",
                    "AI_PROVIDER": "openai",
                    "AI_MODEL": "gpt-5-codex",
                    "OPENAI_API_KEY": "openai-key",
                },
                clear=True,
            ),
        ):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_provider, "openai")
            self.assertEqual(settings.ai_model, "gpt-5-codex")
            self.assertEqual(settings.openai_api_key, "openai-key")

    def test_from_env_default_model_by_provider(self):
        with (
            _NO_DOTENV,
            patch.dict(os.environ, {"GITHUB_TOKEN": "token", "AI_PROVIDER": "ollama"}, clear=True),
        ):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_provider, "ollama")
            self.assertEqual(settings.ai_model, "qwen3:1.7b")

        with (
            _NO_DOTENV,
            patch.dict(os.environ, {"GITHUB_TOKEN": "token", "AI_PROVIDER": "openai"}, clear=True),
        ):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_provider, "openai")
            self.assertEqual(settings.ai_model, "gpt-4o")

    def test_ollama_model_env_fallback(self):
        with _NO_DOTENV, patch.dict(os.environ, {
            "GITHUB_TOKEN": "token",
            "AI_PROVIDER": "ollama",
            "OLLAMA_MODEL": "qwen2.5:1.5b",
        }, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_model, "qwen2.5:1.5b")

    def test_missing_required(self):
        with _NO_DOTENV, patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GITHUB_TOKEN"):
                Settings.from_env()

    def test_missing_jules_key(self):
        with _NO_DOTENV, patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True):
            settings = Settings.from_env()
            self.assertIsNone(settings.jules_api_key)

    def test_boolean_parsing_supports_yes_no(self):
        with (
            _NO_DOTENV,
            patch.dict(
                os.environ,
                {
                    "GITHUB_TOKEN": "token",
                    "PM_AGENT_ENABLED": "YES",
                    "UI_AGENT_ENABLED": "no",
                    "DEV_AGENT_ENABLED": "1",
                    "PR_ASSISTANT_ENABLED": "off",
                    "README_CURATOR_ENABLED": "no",
                },
                clear=True,
            ),
        ):
            settings = Settings.from_env()
            self.assertTrue(settings.enable_product_manager)
            self.assertFalse(settings.enable_interface_developer)
            self.assertTrue(settings.enable_senior_developer)
            self.assertFalse(settings.enable_pr_assistant)
            self.assertFalse(settings.enable_readme_curator)

    def test_invalid_ai_provider_raises(self):
        with (
            _NO_DOTENV,
            patch.dict(
                os.environ,
                {"GITHUB_TOKEN": "token", "ENABLE_AI": "true", "AI_PROVIDER": "invalid"},
                clear=True,
            ),
        ):
            with self.assertRaisesRegex(ValueError, "AI_PROVIDER"):
                Settings.from_env()

    def test_invalid_ai_provider_is_ignored_when_ai_disabled(self):
        with (
            _NO_DOTENV,
            patch.dict(
                os.environ,
                {"GITHUB_TOKEN": "token", "ENABLE_AI": "false", "AI_PROVIDER": "invalid"},
                clear=True,
            ),
        ):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_provider, "litellm")
            self.assertEqual(settings.ai_model, "cloud/auto")

    def test_invalid_agent_interval_raises(self):
        with (
            _NO_DOTENV,
            patch.dict(
                os.environ, {"GITHUB_TOKEN": "token", "AGENT_RUN_INTERVAL_HOURS": "0"}, clear=True
            ),
        ):
            with self.assertRaisesRegex(ValueError, "AGENT_RUN_INTERVAL_HOURS"):
                Settings.from_env()

    def test_non_numeric_agent_interval_raises(self):
        with (
            _NO_DOTENV,
            patch.dict(
                os.environ, {"GITHUB_TOKEN": "token", "AGENT_RUN_INTERVAL_HOURS": "abc"}, clear=True
            ),
        ):
            with self.assertRaisesRegex(ValueError, "AGENT_RUN_INTERVAL_HOURS"):
                Settings.from_env()

    def test_empty_provider_uses_default(self):
        with (
            _NO_DOTENV,
            patch.dict(os.environ, {"GITHUB_TOKEN": "token", "AI_PROVIDER": "   "}, clear=True),
        ):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_provider, "litellm")
            self.assertEqual(settings.ai_model, "cloud/auto")

    def test_invalid_bool_returns_default(self):
        with (
            _NO_DOTENV,
            patch.dict(
                os.environ, {"GITHUB_TOKEN": "token", "PM_AGENT_ENABLED": "invalid"}, clear=True
            ),
        ):
            settings = Settings.from_env()
            self.assertTrue(settings.enable_product_manager)  # Default is True

    def test_positive_int_parsing(self):
        with (
            _NO_DOTENV,
            patch.dict(
                os.environ, {"GITHUB_TOKEN": "token", "AGENT_RUN_INTERVAL_HOURS": "12"}, clear=True
            ),
        ):
            settings = Settings.from_env()
            self.assertEqual(settings.agent_run_interval_hours, 12)

    def test_github_app_settings(self):
        with (
            _NO_DOTENV,
            patch.dict(
                os.environ,
                {
                    "GITHUB_TOKEN": "token",
                    "GITHUB_APP_ID": "3982807",
                    "GITHUB_INSTALLATION_ID": "138493700",
                    "GITHUB_APP_PRIVATE_KEY_PATH": "/secrets/app.pem",
                    "GITHUB_WEBHOOK_SECRET": "secret",
                    "WEBHOOK_DATABASE_PATH": "/data/webhooks.db",
                    "AUTOMATION_MODE": "observe",
                },
                clear=True,
            ),
        ):
            settings = Settings.from_env()
            self.assertEqual(settings.github_app_id, 3982807)
            self.assertEqual(settings.github_installation_id, 138493700)
            self.assertEqual(settings.automation_mode, "observe")

    def test_from_env_gh_pat_fallback(self):
        with (
            _NO_DOTENV,
            patch.dict(os.environ, {"GH_PAT": "pat-token"}, clear=True),
        ):
            settings = Settings.from_env()
            self.assertEqual(settings.github_token, "pat-token")

    @patch("src.webhooks.auth.GitHubAppAuth.installation_token", return_value="app-installed-token")
    def test_from_env_github_app_auto_token(self, mock_inst_token):
        with (
            _NO_DOTENV,
            patch.dict(
                os.environ,
                {
                    "GITHUB_APP_ID": "123",
                    "GITHUB_INSTALLATION_ID": "456",
                    "GITHUB_APP_PRIVATE_KEY_PATH": "/key.pem",
                },
                clear=True,
            ),
        ):
            settings = Settings.from_env()
            self.assertEqual(settings.github_token, "app-installed-token")

    def test_code_reviewer_toggle(self):
        with (
            _NO_DOTENV,
            patch.dict(
                os.environ, {"GITHUB_TOKEN": "token", "CODE_REVIEWER_ENABLED": "false"}, clear=True
            ),
        ):
            settings = Settings.from_env()
            self.assertFalse(settings.enable_code_reviewer)

    def test_every_documented_agent_toggle_is_consumed(self):
        """.env.example must only document toggles that Settings actually reads.

        Guards against the drift where the docs advertised ENABLE_* names that
        settings.py ignored, silently disabling the toggles.
        """
        example = Path(".env.example").read_text(encoding="utf-8")
        documented = set(re.findall(r"^([A-Z][A-Z0-9_]*_ENABLED)=", example, re.M))
        self.assertIn("CODE_REVIEWER_ENABLED", documented)

        env = {"GITHUB_TOKEN": "token", **{name: "false" for name in documented}}
        with _NO_DOTENV, patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()

        enable_attrs = [a for a in dir(settings) if a.startswith("enable_") and a != "enable_ai"]
        self.assertTrue(enable_attrs)
        for attr in enable_attrs:
            self.assertFalse(getattr(settings, attr), f"{attr} ignored its documented toggle")
