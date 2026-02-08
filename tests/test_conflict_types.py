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

        # Mock get_issue_comments to return empty list (no existing conflict comments)
        self.mock_github.get_issue_comments.return_value = []

        # Since the agent now only posts comments instead of resolving conflicts
        # we just need to verify that a comment is posted
        self.agent.handle_conflicts(pr)

        # Verify that a conflict notification comment was posted
        pr.create_issue_comment.assert_called_once()
        comment_text = pr.create_issue_comment.call_args[0][0]

        # Check that the comment contains expected elements
        self.assertIn("⚠️", comment_text)
        self.assertIn("Conflitos de Merge Detectados", comment_text)
        self.assertIn("@juninmd", comment_text)

if __name__ == '__main__':
    unittest.main()
