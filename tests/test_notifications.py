import os
import unittest
from unittest.mock import MagicMock, patch

import requests

from src.github_client import GithubClient


class TestGithubClientNotifications(unittest.TestCase):
    @patch('src.github_client.Github')
    @patch.dict('os.environ', {'GITHUB_TOKEN': 'fake_gh_token', 'TELEGRAM_BOT_TOKEN': 'fake_bot_token', 'TELEGRAM_CHAT_ID': 'fake_chat_id'})
    def setUp(self, mock_github):
        self.client = GithubClient()

    @patch('src.github_client.requests.post')
    def test_send_telegram_notification_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()

        pr = MagicMock()
        pr.title = "Test PR"
        pr.user.login = "testuser"
        pr.html_url = "https://github.com/test/repo/pull/1"
        pr.base.repo.full_name = "test/repo"
        pr.body = "Test description"
        pr.number = 1

        self.client.send_telegram_notification(pr)

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("https://api.telegram.org/botfake_bot_token/sendMessage", args[0])
        payload = kwargs['json']
        self.assertEqual(payload['chat_id'], 'fake_chat_id')
        self.assertIn("🚀 *PR Mergeado\\!*", payload['text'])
        self.assertIn("Test PR", payload['text'])
        self.assertIn("testuser", payload['text'])
        self.assertIn("test/repo", payload['text'])
        # Check for inline keyboard button
        self.assertIn('reply_markup', payload)
        self.assertIn('inline_keyboard', payload['reply_markup'])
        self.assertEqual(payload['reply_markup']['inline_keyboard'][0][0]['text'], "🔗 Ver PR")
        self.assertEqual(payload['reply_markup']['inline_keyboard'][0][0]['url'], "https://github.com/test/repo/pull/1")

    @patch('src.github_client.requests.post')
    @patch('builtins.print')
    def test_send_telegram_notification_missing_credentials(self, mock_print, mock_post):
        self.client.telegram_bot_token = None
        self.client.telegram_chat_id = None

        pr = MagicMock()
        self.client.send_telegram_notification(pr)

        mock_post.assert_not_called()
        mock_print.assert_any_call("Telegram credentials missing. Skipping notification.")

    @patch('src.github_client.requests.post')
    @patch('builtins.print')
    def test_send_telegram_notification_error(self, mock_print, mock_post):
        mock_post.side_effect = Exception("Network error")

        pr = MagicMock()
        pr.number = 1
        pr.title = "Test PR"
        pr.user.login = "testuser"
        pr.html_url = "https://github.com/test/repo/pull/1"
        pr.base.repo.full_name = "test/repo"
        pr.body = "Test description"

        self.client.send_telegram_notification(pr)

        # Updated to match actual error handling in github_client.py
        # It catches Exception and prints "Failed to send Telegram message: ..."
        mock_print.assert_any_call("Failed to send Telegram message: Network error")

if __name__ == '__main__':
    unittest.main()
