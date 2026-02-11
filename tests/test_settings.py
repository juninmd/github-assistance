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

    def test_from_env_custom(self):
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "token",
            "JULES_API_KEY": "key",
            "AI_PROVIDER": "ollama",
            "AI_MODEL": "llama3",
            "OLLAMA_BASE_URL": "http://ollama:11434"
        }, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.ai_provider, "ollama")
            self.assertEqual(settings.ai_model, "llama3")
            self.assertEqual(settings.ollama_base_url, "http://ollama:11434")

    def test_missing_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GITHUB_TOKEN"):
                Settings.from_env()

        with patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True):
            with self.assertRaisesRegex(ValueError, "JULES_API_KEY"):
                Settings.from_env()
