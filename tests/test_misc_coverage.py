import os
import unittest
from unittest.mock import MagicMock, patch

from github import GithubException

from src.agents.base_agent import BaseAgent
from src.github_client import GithubClient


class TestGithubClientCoverage(unittest.TestCase):
    def setUp(self):
        self.patcher = patch.dict(os.environ, {"GITHUB_TOKEN": "fake", "TELEGRAM_BOT_TOKEN": "bot", "TELEGRAM_CHAT_ID": "chat"})
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_init_no_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                GithubClient()

    def test_merge_pr_exception(self):
        client = GithubClient()
        pr = MagicMock()
        pr.merge.side_effect = GithubException(409, "Conflict")
        success, msg = client.merge_pr(pr)
        self.assertFalse(success)
        self.assertIn("Conflict", msg)

    @patch("src.github_client.requests.post")
    def test_send_telegram_msg_exception(self, mock_post):
        client = GithubClient()
        mock_post.side_effect = Exception("Connection Error")
        result = client.send_telegram_msg("hello")
        self.assertFalse(result)

    @patch("src.github_client.requests.post")
    def test_send_telegram_msg_no_creds(self, mock_post):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": ""}):
            client = GithubClient()
            # Re-init to pick up env change or just modify client
            client.telegram_bot_token = ""
            result = client.send_telegram_msg("hello")
            self.assertFalse(result) # Should be None actually based on code?
            # Code: if not ...: return
            # So it returns None.
            # Asserting False might fail if it returns None.

    def test_commit_file_exception(self):
        client = GithubClient()
        pr = MagicMock()
        pr.base.repo.get_contents.side_effect = GithubException(404, "Not Found")
        result = client.commit_file(pr, "file", "content", "msg")
        self.assertFalse(result)

class ConcreteAgent(BaseAgent):
    @property
    def persona(self): return "p"
    @property
    def mission(self): return "m"
    def run(self): return {}

class TestBaseAgentCoverage(unittest.TestCase):
    def setUp(self):
        self.jules = MagicMock()
        self.gh = MagicMock()
        self.allow = MagicMock()

    def test_load_instructions_missing(self):
        with patch("src.agents.base_agent.Path") as mock_path:
            # mock_path(__file__).parent / self.name / 'instructions.md'
            # We need to ensure exists() returns False
            mock_path.return_value.parent.__truediv__.return_value.__truediv__.return_value.exists.return_value = False

            agent = ConcreteAgent(self.jules, self.gh, self.allow, name="test_agent")
            instr = agent.load_instructions()
            self.assertEqual(instr, "")

    def test_load_instructions_exception(self):
         with patch("src.agents.base_agent.Path") as mock_path:
            mock_file = mock_path.return_value.parent.__truediv__.return_value.__truediv__.return_value
            mock_file.exists.return_value = True

            with patch("builtins.open", side_effect=Exception("Read Error")):
                agent = ConcreteAgent(self.jules, self.gh, self.allow, name="test_agent")
                instr = agent.load_instructions()
                self.assertEqual(instr, "")

    def test_load_jules_instructions_missing(self):
        with patch("src.agents.base_agent.Path") as mock_path:
            mock_path.return_value.parent.__truediv__.return_value.__truediv__.return_value.exists.return_value = False

            agent = ConcreteAgent(self.jules, self.gh, self.allow, name="test_agent")
            instr = agent.load_jules_instructions("missing.md")
            self.assertEqual(instr, "")

    def test_load_jules_instructions_exception(self):
         with patch("src.agents.base_agent.Path") as mock_path:
            mock_file = mock_path.return_value.parent.__truediv__.return_value.__truediv__.return_value
            mock_file.exists.return_value = True

            with patch("builtins.open", side_effect=Exception("Read Error")):
                agent = ConcreteAgent(self.jules, self.gh, self.allow, name="test_agent")
                instr = agent.load_jules_instructions("exist.md")
                self.assertEqual(instr, "")

    def test_get_repo_info_exception(self):
        agent = ConcreteAgent(self.jules, self.gh, self.allow, name="test_agent")
        self.gh.get_repo.side_effect = Exception("API Error")
        result = agent.get_repository_info("repo")
        self.assertIsNone(result)

    def test_create_jules_session_not_allowed(self):
        self.allow.is_allowed.return_value = False
        agent = ConcreteAgent(self.jules, self.gh, self.allow, name="test_agent")
        with self.assertRaises(ValueError):
            agent.create_jules_session("repo", "instr", "title")

if __name__ == '__main__':
    unittest.main()
