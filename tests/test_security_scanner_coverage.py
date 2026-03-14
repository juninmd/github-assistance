
import unittest
from unittest.mock import MagicMock

from src.agents.security_scanner import telegram_summary
from src.agents.security_scanner.telegram_summary import _send_lines, _send_repo_block


class TestTelegramSummaryCoverage(unittest.TestCase):
    def test_telegram_summary_send_lines_truncate(self):
        telegram = MagicMock()
        telegram._truncate = lambda x: x[:10]
        old_max = telegram_summary._MAX_LEN
        telegram_summary._MAX_LEN = 10
        _send_lines(["A"*15], telegram)
        telegram.send_message.assert_called_once()
        self.assertEqual(len(telegram.send_message.call_args[0][0]), 10)
        telegram_summary._MAX_LEN = old_max

    def test_telegram_summary_send_lines_split_append(self):
        telegram = MagicMock()
        telegram._truncate = lambda x: x
        old_max = telegram_summary._MAX_LEN
        telegram_summary._MAX_LEN = 10
        _send_lines(["A"*5, "B"*6], telegram)
        self.assertEqual(telegram.send_message.call_count, 2)
        telegram_summary._MAX_LEN = old_max

    def test_telegram_summary_send_repo_block_truncate_full(self):
        telegram = MagicMock()
        telegram.escape = lambda x: x
        telegram._truncate = lambda x: x[:10]
        old_max = telegram_summary._MAX_LEN
        telegram_summary._MAX_LEN = 10
        finding = {"rule_id": "rule1", "file": "file1", "line": 1, "full_commit": "commit1"}
        _send_repo_block("owner/repo", [finding], telegram, telegram.escape, lambda r, c: "author")
        telegram.send_message.assert_called_once()
        self.assertEqual(len(telegram.send_message.call_args[0][0]), 10)
        telegram_summary._MAX_LEN = old_max

    def test_send_repo_block_unknown_author(self):
        telegram = MagicMock()
        telegram.escape = lambda x: x
        telegram._truncate = lambda x: x
        finding = {"rule_id": "r", "file": "f", "line": 1, "full_commit": "c"}
        _send_repo_block("repo", [finding], telegram, telegram.escape, lambda r, c: "unknown")
        telegram.send_message.assert_called_once()
        self.assertIn("unknown", telegram.send_message.call_args[0][0])
