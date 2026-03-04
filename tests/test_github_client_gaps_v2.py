import os
import unittest
from unittest.mock import MagicMock, patch

from github import GithubException

from src.github_client import GithubClient


class TestGithubClientGapsV2(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "token", "TELEGRAM_BOT_TOKEN": "bot", "TELEGRAM_CHAT_ID": "chat"}):
            self.client = GithubClient()

    def test_close_pr_exception(self):
        pr = MagicMock()
        pr.edit.side_effect = GithubException(400, "Error")
        success, msg = self.client.close_pr(pr)
        self.assertFalse(success)
        self.assertIn("Error", msg)

    def test_send_telegram_notification_truncate_body(self):
        pr = MagicMock()
        pr.title = "title"
        pr.user.login = "user"
        pr.base.repo.full_name = "repo"
        pr.html_url = "url"
        pr.body = "a" * 500

        with patch.object(self.client, "send_telegram_msg") as mock_send:
            self.client.send_telegram_notification(pr)

            # verify it sent the msg
            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            text = args[0]
            self.assertIn(r"\.\.\.", text)

    def test_accept_review_suggestions_invalid_line(self):
        pr = MagicMock()
        comment = MagicMock()
        comment.user.login = "bot"
        comment.body = "```suggestion\nnew_code\n```"
        comment.path = "file.py"
        comment.line = 0 # invalid
        comment.start_line = None
        pr.get_review_comments.return_value = [comment]

        success, msg, count = self.client.accept_review_suggestions(pr, ["bot"])
        self.assertTrue(success)
        self.assertEqual(count, 0)

    def test_accept_review_suggestions_start_line(self):
        pr = MagicMock()
        comment = MagicMock()
        comment.user.login = "bot"
        comment.body = "```suggestion\nnew_code\n```"
        comment.path = "file.py"
        comment.line = 5
        comment.start_line = 3
        pr.get_review_comments.return_value = [comment]

        pr.head.repo.get_contents.return_value.decoded_content = b"1\n2\n3\n4\n5\n6\n"
        pr.head.repo.get_contents.return_value.sha = "sha"

        success, msg, count = self.client.accept_review_suggestions(pr, ["bot"])
        self.assertTrue(success)
        self.assertEqual(count, 1)

    def test_accept_review_suggestions_no_suggestions(self):
        pr = MagicMock()
        comment = MagicMock()
        comment.user.login = "bot"
        comment.body = "No suggestions here"
        pr.get_review_comments.return_value = [comment]

        success, msg, count = self.client.accept_review_suggestions(pr, ["bot"])
        self.assertTrue(success)
        self.assertEqual(count, 0)

    def test_accept_review_suggestions_no_suggestions_in_file(self):
        pr = MagicMock()
        comment = MagicMock()
        comment.user.login = "bot"
        comment.body = "```suggestion\nnew\n```"
        comment.path = "file.py"
        comment.line = 1
        comment.start_line = None
        pr.get_review_comments.return_value = [comment]

        # force exception inside file loop
        pr.head.repo.get_contents.side_effect = Exception("error")

        success, msg, count = self.client.accept_review_suggestions(pr, ["bot"])
        self.assertTrue(success)
        self.assertEqual(count, 0)


    def test_normalize_login_bot(self):
        login = "bot[bot]"
        self.assertEqual(self.client._normalize_login(login), "bot")

    def test_accept_review_suggestions_not_bot(self):
        pr = MagicMock()
        comment = MagicMock()
        comment.user.login = "other"
        comment.body = "```suggestion\nnew_code\n```"
        comment.path = "file.py"
        comment.line = 5
        comment.start_line = 3
        pr.get_review_comments.return_value = [comment]

        success, msg, count = self.client.accept_review_suggestions(pr, ["bot"])
        self.assertTrue(success)
        self.assertEqual(count, 0)


    def test_close_pr_success(self):
        pr = MagicMock()
        success, msg = self.client.close_pr(pr)
        pr.edit.assert_called_with(state="closed")
        self.assertTrue(success)
        self.assertEqual(msg, "PR closed successfully")
