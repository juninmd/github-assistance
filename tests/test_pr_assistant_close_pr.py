import unittest
from unittest.mock import MagicMock, patch

from src.agents.pr_assistant.agent import PRAssistantAgent


class TestPRAssistantClosePR(unittest.TestCase):
    def setUp(self):
        self.agent = PRAssistantAgent(
            MagicMock(),
            MagicMock(),
            MagicMock(),
            target_owner="owner",
            allowed_authors=["trusted-reviewer", "author"],
        )

    def test_close_pr_from_trusted_comment(self):
        pr = MagicMock()
        pr.user.login = "author"
        pr.number = 10
        pr.title = "Test"
        pr.base.repo.full_name = "owner/repo"
        pr.body = "regular body"

        comment = MagicMock()
        comment.body = "Please close PR, I do not agree with this change"
        comment.user.login = "trusted-reviewer"

        self.agent.github_client.get_issue_comments.return_value = [comment]
        self.agent.github_client.close_pr.return_value = (True, "ok")

        result = self.agent.process_pr(pr)

        self.assertEqual(result["action"], "closed")
        self.agent.github_client.close_pr.assert_called_once_with(pr)

    def test_ignore_close_request_from_untrusted_comment(self):
        pr = MagicMock()
        pr.user.login = "author"
        pr.number = 11
        pr.title = "Test"
        pr.base.repo.full_name = "owner/repo"
        pr.body = "regular body"
        pr.mergeable = True

        comment = MagicMock()
        comment.body = "close pr"
        comment.user.login = "random-user"

        self.agent.github_client.get_issue_comments.return_value = [comment]
        self.agent.github_client.accept_review_suggestions.return_value = (True, "", 0)

        with patch.object(self.agent, "is_pr_too_young", return_value=False), patch.object(
            self.agent, "check_pipeline_status", return_value={"success": False, "reason": "pending"}
        ):
            result = self.agent.process_pr(pr)

        self.assertEqual(result["action"], "skipped")
        self.agent.github_client.close_pr.assert_not_called()


if __name__ == "__main__":
    unittest.main()
