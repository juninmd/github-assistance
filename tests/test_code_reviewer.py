"""Tests for Code Reviewer Agent."""
import unittest
from unittest.mock import MagicMock, patch

from src.agents.code_reviewer.agent import CodeReviewerAgent
from src.config.repository_allowlist import RepositoryAllowlist
from src.github_client import GithubClient
from src.jules.client import JulesClient
from src.notifications.telegram import TelegramNotifier


class TestCodeReviewerAgent(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock(spec=JulesClient)
        self.github_client = MagicMock(spec=GithubClient)
        self.allowlist = MagicMock(spec=RepositoryAllowlist)
        self.telegram = MagicMock(spec=TelegramNotifier)

        self.agent = CodeReviewerAgent(
            jules_client=self.jules_client,
            github_client=self.github_client,
            allowlist=self.allowlist,
            telegram=self.telegram,
            ai_provider="gemini",
            ai_model="gemini-2.5-flash",
            enforce_repository_allowlist=True,
        )

    def test_init(self):
        self.assertEqual(self.agent.name, "code_reviewer")
        self.assertEqual(self.agent.ai_provider, "gemini")
        self.assertEqual(self.agent.ai_model, "gemini-2.5-flash")

    def test_persona(self):
        persona = self.agent.persona
        self.assertIn("Code Reviewer", persona)
        self.assertIn("code quality", persona.lower())

    def test_mission(self):
        mission = self.agent.mission
        self.assertIn("Review pull requests", mission)
        self.assertIn("best practices", mission.lower())

    def test_run_no_repositories(self):
        self.allowlist.list_repositories.return_value = []

        result = self.agent.run()

        self.assertEqual(result["reviews_performed"], [])
        self.assertEqual(result["failed"], [])
        self.assertIn("metrics", result)

    @patch.object(CodeReviewerAgent, "_find_open_prs")
    def test_run_no_prs(self, mock_find_prs):
        self.allowlist.list_repositories.return_value = ["owner/repo1"]
        mock_find_prs.return_value = []

        result = self.agent.run()

        self.assertEqual(result["reviews_performed"], [])
        mock_find_prs.assert_called_once_with("owner/repo1")

    @patch.object(CodeReviewerAgent, "_send_summary")
    @patch.object(CodeReviewerAgent, "_review_pull_request")
    @patch.object(CodeReviewerAgent, "_has_recent_review")
    @patch.object(CodeReviewerAgent, "_find_open_prs")
    def test_run_with_prs(self, mock_find_prs, mock_has_recent, mock_review, mock_send):
        self.allowlist.list_repositories.return_value = ["owner/repo1"]

        mock_pr = MagicMock()
        mock_pr.number = 123
        mock_find_prs.return_value = [mock_pr]
        mock_has_recent.return_value = False
        mock_review.return_value = {"success": True, "pr_number": 123}

        result = self.agent.run()

        self.assertEqual(len(result["reviews_performed"]), 1)
        self.assertEqual(result["reviews_performed"][0]["pr_number"], 123)
        mock_review.assert_called_once_with(mock_pr)
        mock_send.assert_called_once()

    @patch.object(CodeReviewerAgent, "_send_summary")
    @patch.object(CodeReviewerAgent, "_review_pull_request")
    @patch.object(CodeReviewerAgent, "_has_recent_review")
    @patch.object(CodeReviewerAgent, "_find_open_prs")
    def test_run_skip_recently_reviewed(self, mock_find_prs, mock_has_recent, mock_review, mock_send):
        self.allowlist.list_repositories.return_value = ["owner/repo1"]

        mock_pr = MagicMock()
        mock_pr.number = 123
        mock_find_prs.return_value = [mock_pr]
        mock_has_recent.return_value = True  # Already reviewed

        result = self.agent.run()

        self.assertEqual(len(result["reviews_performed"]), 0)
        mock_review.assert_not_called()

    @patch.object(CodeReviewerAgent, "_send_summary")
    @patch.object(CodeReviewerAgent, "_review_pull_request")
    @patch.object(CodeReviewerAgent, "_has_recent_review")
    @patch.object(CodeReviewerAgent, "_find_open_prs")
    def test_run_review_failure(self, mock_find_prs, mock_has_recent, mock_review, mock_send):
        self.allowlist.list_repositories.return_value = ["owner/repo1"]

        mock_pr = MagicMock()
        mock_pr.number = 123
        mock_find_prs.return_value = [mock_pr]
        mock_has_recent.return_value = False
        mock_review.return_value = {"success": False, "pr_number": 123}

        result = self.agent.run()

        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(len(result["reviews_performed"]), 0)

    @patch.object(CodeReviewerAgent, "_send_summary")
    @patch.object(CodeReviewerAgent, "_review_pull_request")
    @patch.object(CodeReviewerAgent, "_has_recent_review")
    @patch.object(CodeReviewerAgent, "_find_open_prs")
    def test_run_exception_handling(self, mock_find_prs, mock_has_recent, mock_review, mock_send):
        self.allowlist.list_repositories.return_value = ["owner/repo1"]

        mock_pr = MagicMock()
        mock_pr.number = 123
        mock_find_prs.return_value = [mock_pr]
        mock_has_recent.return_value = False
        mock_review.side_effect = Exception("Review failed")

        result = self.agent.run()

        self.assertEqual(len(result["failed"]), 1)
        self.assertIn("error", result["failed"][0])

    def test_find_open_prs(self):
        # Test placeholder implementation
        result = self.agent._find_open_prs("owner/repo")
        self.assertEqual(result, [])

    def test_has_recent_review(self):
        # Test placeholder implementation
        mock_pr = MagicMock()
        result = self.agent._has_recent_review(mock_pr)
        self.assertFalse(result)

    def test_review_pull_request(self):
        # Test placeholder implementation
        mock_pr = MagicMock()
        mock_pr.number = 123

        result = self.agent._review_pull_request(mock_pr)

        self.assertTrue(result["success"])
        self.assertEqual(result["pr_number"], 123)

    def test_send_summary_no_reviews(self):
        self.agent._send_summary([], [])
        self.telegram.send_message.assert_not_called()

    def test_send_summary_with_reviews(self):
        reviews = [{"pr_number": 123}]
        failures = []

        self.agent._send_summary(reviews, failures)

        self.telegram.send_message.assert_called_once()
        call_args = self.telegram.send_message.call_args
        message = call_args[0][0]
        self.assertIn("Code Review Summary", message)
        self.assertIn("Reviews: *1*", message)
