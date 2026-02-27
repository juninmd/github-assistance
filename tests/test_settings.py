import unittest
import os
from unittest.mock import patch
from src.config.settings import Settings


class TestSettings(unittest.TestCase):
    def test_from_env_defaults(self):
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "token",
            "JULES_API_KEY": "key"
        }, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_provider, "gemini")
            self.assertEqual(settings.ai_model, "gemini-2.5-flash")
            self.assertEqual(settings.ollama_base_url, "http://localhost:11434")
            self.assertIsNone(settings.openai_api_key)

    def test_from_env_custom(self):
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "token",
            "JULES_API_KEY": "key",
            "AI_PROVIDER": "openai",
            "AI_MODEL": "gpt-5-codex",
            "OPENAI_API_KEY": "openai-key"
        }, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_provider, "openai")
            self.assertEqual(settings.ai_model, "gpt-5-codex")
            self.assertEqual(settings.openai_api_key, "openai-key")

    def test_from_env_default_model_by_provider(self):
        # Test default model for ollama
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "token",
            "AI_PROVIDER": "ollama"
        }, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_provider, "ollama")
            self.assertEqual(settings.ai_model, "llama3")

        # Test default model for openai
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "token",
            "AI_PROVIDER": "openai"
        }, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_provider, "openai")
            self.assertEqual(settings.ai_model, "gpt-4o")

    def test_missing_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GITHUB_TOKEN"):
                Settings.from_env()

    def test_missing_jules_key(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True):
            settings = Settings.from_env()
            self.assertIsNone(settings.jules_api_key)

    def test_boolean_parsing_supports_yes_no(self):
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "token",
            "PM_AGENT_ENABLED": "YES",
            "UI_AGENT_ENABLED": "no",
            "DEV_AGENT_ENABLED": "1",
            "PR_ASSISTANT_ENABLED": "off",
        }, clear=True):
            settings = Settings.from_env()
            self.assertTrue(settings.product_manager_enabled)
            self.assertFalse(settings.interface_developer_enabled)
            self.assertTrue(settings.senior_developer_enabled)
            self.assertFalse(settings.pr_assistant_enabled)

    def test_invalid_ai_provider_raises(self):
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "token",
            "AI_PROVIDER": "invalid"
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "AI_PROVIDER"):
                Settings.from_env()

    def test_invalid_agent_interval_raises(self):
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "token",
            "AGENT_RUN_INTERVAL_HOURS": "0"
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "AGENT_RUN_INTERVAL_HOURS"):
                Settings.from_env()

    def test_invalid_bool_returns_default(self):
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "token",
            "PM_AGENT_ENABLED": "invalid"
        }, clear=True):
            settings = Settings.from_env()
            self.assertTrue(settings.product_manager_enabled)  # Default is True

    def test_positive_int_parsing(self):
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "token",
            "AGENT_RUN_INTERVAL_HOURS": "12"
        }, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.agent_run_interval_hours, 12)
