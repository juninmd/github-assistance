import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from src.agents.base_agent import BaseAgent
from src.agents.security_scanner.agent import SecurityScannerAgent
from src.github_client import GithubClient
from src.main import main as legacy_main


class TestMiscCoverageGaps(unittest.TestCase):
    def test_security_scanner_escape_empty(self):
        agent = SecurityScannerAgent(
            MagicMock(), MagicMock(), MagicMock()
        )
        self.assertEqual(agent._escape_telegram(""), "")

    def test_security_scanner_get_repos_exception(self):
        mock_github = MagicMock()
        mock_github.g.get_user.side_effect = Exception("API Error")
        agent = SecurityScannerAgent(
            MagicMock(), mock_github, MagicMock()
        )
        repos = agent._get_all_repositories()
        self.assertEqual(repos, [])

    def test_base_agent_get_instructions_nested(self):
        # Subclass BaseAgent to test abstract method
        class TestAgent(BaseAgent):
            @property
            def persona(self): return ""
            @property
            def mission(self): return ""
            def run(self): pass

        agent = TestAgent(MagicMock(), MagicMock(), MagicMock())

        # Mock load_instructions
        instructions = """
## Section 1
Content 1
### Subsection
Content 1.1
## Section 2
Content 2
"""
        with patch.object(agent, 'load_instructions', return_value=instructions):
            # Test getting section 1, should stop at section 2 (same level)
            content = agent.get_instructions_section("## Section 1")
            self.assertIn("Content 1", content)
            self.assertIn("### Subsection", content)
            self.assertNotIn("## Section 2", content)

    @patch("src.main.Settings")
    @patch("src.main.sys.exit")
    def test_legacy_main_exception(self, mock_exit, mock_settings):
        mock_settings.from_env.side_effect = Exception("Config Error")
        legacy_main()
        mock_exit.assert_called_with(1)

    def test_github_client_token_missing(self):
        # Save env
        old_token = os.environ.get("GITHUB_TOKEN")
        if old_token:
            del os.environ["GITHUB_TOKEN"]

        try:
            with self.assertRaises(ValueError):
                GithubClient(token=None)
        finally:
            if old_token:
                os.environ["GITHUB_TOKEN"] = old_token

    def test_github_client_telegram_missing_creds(self):
        # Ensure env vars are missing
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.github_client.os.environ.get") as mock_get:
                mock_get.side_effect = lambda k: "test" if k == "GITHUB_TOKEN" else None
                client = GithubClient(token="test")
                # Should return None/False and print message
                result = client.send_telegram_msg("test")
                self.assertIsNone(result)

    def test_github_client_telegram_exception(self):
        client = GithubClient(token="test")
        client.telegram_bot_token = "token"
        client.telegram_chat_id = "chat"

        with patch("src.github_client.requests.post", side_effect=Exception("Network Error")):
             result = client.send_telegram_msg("test")
             self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
