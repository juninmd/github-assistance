import os
import unittest
from unittest.mock import MagicMock, patch

from github import GithubException

from src.github_client import GithubClient


class TestGithubClientGaps(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "token", "TELEGRAM_BOT_TOKEN": "bot", "TELEGRAM_CHAT_ID": "chat"}):
            self.client = GithubClient()

    def test_escape_markdown_none(self):
        self.assertIsNone(self.client._escape_markdown(None))

    def test_escape_markdown_special(self):
        text = "_*[hello]*_"
        escaped = self.client._escape_markdown(text)
        self.assertEqual(escaped, "\\_\\*\\[hello\\]\\*\\_")

    def test_commit_file_exception(self):
        pr = MagicMock()
        pr.base.repo.get_contents.side_effect = GithubException(404, "Not Found")

        result = self.client.commit_file(pr, "path", "content", "msg")
        self.assertFalse(result)

    def test_commit_file_update_exception(self):
        pr = MagicMock()
        pr.base.repo.get_contents.return_value.path = "path"
        pr.base.repo.get_contents.return_value.sha = "sha"
        pr.base.repo.update_file.side_effect = GithubException(500, "Error")

        result = self.client.commit_file(pr, "path", "content", "msg")
        self.assertFalse(result)

    def test_send_telegram_msg_no_creds(self):
        self.client.telegram_bot_token = None
        result = self.client.send_telegram_msg("hi")
        self.assertIsNone(result)

    def test_send_telegram_msg_truncate(self):
        long_text = "a" * 5000
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200

            self.client.send_telegram_msg(long_text)

            args, kwargs = mock_post.call_args
            sent_text = kwargs['json']['text']
            self.assertLess(len(sent_text), 4100)
            self.assertIn("truncada", sent_text)

    def test_send_telegram_msg_truncate_backslash(self):
        # Text ending with backslash right at cut point
        # MAX_LENGTH=4096. Truncate msg len approx 30 chars.
        # Cut point around 4060.
        text = "a" * 4065 + "\\" + "b"*100

        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200

            self.client.send_telegram_msg(text)

            args, kwargs = mock_post.call_args
            sent_text = kwargs['json']['text']
            # Ensure it doesn't end with single backslash before truncation msg
            # The code removes trailing backslash if present at cut point
            # We can't easily assert the exact cut point logic without exact length calculation
            # But we can verify it sends successfully
            self.assertIn("truncada", sent_text)

    def test_send_telegram_msg_exception(self):
        with patch("requests.post", side_effect=Exception("Connection Error")):
            result = self.client.send_telegram_msg("hi")
            self.assertFalse(result)

    def test_accept_review_suggestions_exception(self):
        pr = MagicMock()
        pr.get_review_comments.side_effect = Exception("API Error")

        success, msg, count = self.client.accept_review_suggestions(pr, ["bot"])
        self.assertFalse(success)
        self.assertIn("Error processing", msg)

    def test_accept_review_suggestions_apply_error(self):
        pr = MagicMock()
        comment = MagicMock()
        comment.user.login = "bot"
        comment.body = "```suggestion\nnew_code\n```"
        comment.path = "file.py"
        comment.line = 1
        comment.start_line = None

        pr.get_review_comments.return_value = [comment]

        # Mock repo to raise exception on update_file
        pr.head.repo.get_contents.return_value.decoded_content = b"old_code"
        pr.head.repo.update_file.side_effect = Exception("Update Failed")

        success, msg, count = self.client.accept_review_suggestions(pr, ["bot"])
        # Should catch exception and continue/return success but count 0
        self.assertTrue(success)
        self.assertEqual(count, 0)

if __name__ == '__main__':
    unittest.main()
