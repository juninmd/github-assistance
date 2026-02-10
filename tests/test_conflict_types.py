import unittest
import subprocess
from unittest.mock import MagicMock, patch
from src.agents.pr_assistant.agent import PRAssistantAgent

class TestConflictTypes(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True

        # Patch AI client initialization to avoid API key error
        with patch("src.agents.pr_assistant.agent.GeminiClient"):
            self.agent = PRAssistantAgent(self.mock_github, self.mock_jules, self.mock_allowlist)

    @patch("src.agents.pr_assistant.agent.subprocess")
    @patch("src.agents.pr_assistant.agent.os")
    @patch("builtins.open")
    def test_handle_conflicts_AA(self, mock_open, mock_os, mock_subprocess):
        # Fix: Assign real Exception class to the mock
        mock_subprocess.CalledProcessError = subprocess.CalledProcessError

        # Simulate a PR with "Both Added" conflict
        pr = MagicMock()
        pr.number = 10
        pr.mergeable = False
        pr.user.login = "juninmd"
        pr.head.repo.full_name = "fork/repo"
        pr.base.repo.full_name = "base/repo"
        # Set IDs to simulate fork
        pr.head.repo.id = 1
        pr.base.repo.id = 2

        # Mock get_issue_comments to return empty list (no existing conflict comments)
        self.mock_github.get_issue_comments.return_value = []

        # Mock autonomous resolution to succeed
        with patch.object(self.agent, 'resolve_conflicts_autonomously', return_value=True) as mock_resolve:
             result = self.agent.handle_conflicts(pr)

             mock_resolve.assert_called_once()
             self.assertEqual(result["action"], "conflicts_resolved")

if __name__ == '__main__':
    unittest.main()
