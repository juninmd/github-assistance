import unittest
from unittest.mock import MagicMock, patch

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

    def test_send_message_missing_creds(self):
        notifier = TelegramNotifier()
        result = notifier.send_message("text")
        self.assertFalse(result)

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
