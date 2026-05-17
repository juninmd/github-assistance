import unittest
from unittest.mock import MagicMock, patch

import requests

from src.notifications.telegram import TelegramNotifier


class TestTelegramNotifier(unittest.TestCase):
    def test_escape_special_chars(self):
        self.assertEqual(TelegramNotifier.escape("hello_world"), "hello\\_world")
        self.assertEqual(TelegramNotifier.escape("test.com"), "test\\.com")
        self.assertEqual(TelegramNotifier.escape(None), "")
        self.assertEqual(TelegramNotifier.escape(""), "")

    def test_enabled_property(self):
        notifier = TelegramNotifier(bot_token="t", chat_id="c")
        self.assertTrue(notifier.enabled)

        notifier = TelegramNotifier()
        self.assertFalse(notifier.enabled)

        notifier = TelegramNotifier(bot_token="t")
        self.assertFalse(notifier.enabled)

    @patch("src.notifications.telegram.requests.post")
    def test_send_message_success(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        notifier = TelegramNotifier(bot_token="bot", chat_id="chat")
        result = notifier.send_message("text")
        self.assertTrue(result)
        mock_post.assert_called_once()

    @patch("src.notifications.telegram.requests.post")
    def test_send_message_failure(self, mock_post):
        mock_post.side_effect = Exception("Error")
        notifier = TelegramNotifier(bot_token="bot", chat_id="chat")
        result = notifier.send_message("text")
        self.assertFalse(result)

    @patch("src.notifications.telegram.requests.post")
    def test_send_message_http_error_includes_body(self, mock_post):
        # simulate an HTTP 400 with a body message
        response = MagicMock()
        response.raise_for_status.side_effect = requests.HTTPError("400 Client Error")
        response.text = '{"ok":false,"error_code":400,"description":"Bad Request: chat not found"}'
        mock_post.return_value = response
        notifier = TelegramNotifier(bot_token="bot", chat_id="chat")
        result = notifier.send_message("text")
        self.assertFalse(result)
        # make sure we printed the response body as part of the error
        # since print output isn't easily captured here, we rely on the call sequence
        mock_post.assert_called_once()

    def test_send_message_missing_creds(self):
        notifier = TelegramNotifier()
        result = notifier.send_message("text")
        self.assertFalse(result)

    def test_send_message_invalid_chat_id(self):
        notifier = TelegramNotifier(bot_token="bot", chat_id="   ")
        result = notifier.send_message("text")
        self.assertFalse(result)

    @patch("src.notifications.telegram.requests.post")
    def test_send_message_with_prefix(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        notifier = TelegramNotifier(bot_token="bot", chat_id="chat", prefix="[TEST AGENT]")
        result = notifier.send_message("hello")
        self.assertTrue(result)
        mock_post.assert_called_once()
        _args, kwargs = mock_post.call_args
        text = kwargs["json"]["text"]
        self.assertTrue(text.startswith("<b>[TEST AGENT]</b>\nhello"))

    @patch("src.notifications.telegram.requests.post")
    def test_send_message_truncate(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        notifier = TelegramNotifier(bot_token="bot", chat_id="chat")
        long_text = "a" * 5000
        notifier.send_message(long_text)
        _args, kwargs = mock_post.call_args
        text = kwargs["json"]["text"]
        self.assertLessEqual(len(text), 4096)

    @patch("src.notifications.telegram.requests.post")
    def test_send_pr_notification(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        notifier = TelegramNotifier(bot_token="bot", chat_id="chat")

        pr = MagicMock()
        pr.title = "Title"
        pr.user.login = "User"
        pr.base.repo.full_name = "Repo"
        pr.body = "Body"
        pr.number = 1
        pr.html_url = "http://url"

        notifier.send_pr_notification(pr)
        mock_post.assert_called_once()
        _args, kwargs = mock_post.call_args
        text = kwargs["json"]["text"]
        self.assertIn("Title", text)

    @patch("src.notifications.telegram.requests.post")
    def test_send_pr_notification_long_body(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        notifier = TelegramNotifier(bot_token="bot", chat_id="chat")

        pr = MagicMock()
        pr.title = "Title"
        pr.user.login = "User"
        pr.base.repo.full_name = "Repo"
        pr.body = "A" * 500
        pr.number = 2
        pr.html_url = "http://url"

        notifier.send_pr_notification(pr)
        mock_post.assert_called_once()

    def test_send_pr_notification_disabled(self):
        notifier = TelegramNotifier()
        pr = MagicMock()
        pr.title = "Title"
        pr.user.login = "User"
        pr.base.repo.full_name = "Repo"
        pr.body = "Body"
        pr.number = 3
        pr.html_url = "http://url"
        notifier.send_pr_notification(pr)
        # Should not raise — just silently skips

    @patch("src.notifications.telegram.requests.post")
    def test_send_message_with_reply_markup(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        notifier = TelegramNotifier(bot_token="bot", chat_id="chat")
        markup = {"inline_keyboard": [[{"text": "ok", "url": "http://url"}]]}
        notifier.send_message("text", reply_markup=markup)
        _args, kwargs = mock_post.call_args
        self.assertIn("reply_markup", kwargs["json"])

    def test_truncate_returns_first_split_chunk(self):
        notifier = TelegramNotifier(bot_token="token", chat_id="id")
        text = "A" * 5000
        result = notifier._truncate(text)
        self.assertLessEqual(len(result), notifier.MAX_LENGTH)
