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

    def test_missing_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GITHUB_TOKEN"):
                Settings.from_env()

    def test_missing_jules_key(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True):
            settings = Settings.from_env()
            self.assertIsNone(settings.jules_api_key)
