"""Tests for the retry decorator (exponential backoff + jitter)."""

import unittest
from unittest.mock import patch

import requests

from src.utils.retry import with_retry


class TestWithRetry(unittest.TestCase):
    def test_returns_first_success_without_sleeping(self):
        calls = []

        @with_retry(max_attempts=3)
        def ok():
            calls.append(1)
            return "done"

        with patch("src.utils.retry.time.sleep") as sleep:
            self.assertEqual(ok(), "done")
        self.assertEqual(len(calls), 1)
        sleep.assert_not_called()

    def test_retries_retryable_error_then_succeeds(self):
        attempts = {"n": 0}

        @with_retry(max_attempts=3, base_delay=0)
        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise requests.ConnectionError("boom")
            return "ok"

        with patch("src.utils.retry.time.sleep"):
            self.assertEqual(flaky(), "ok")
        self.assertEqual(attempts["n"], 3)

    def test_non_retryable_error_raises_immediately(self):
        attempts = {"n": 0}

        @with_retry(max_attempts=3)
        def bad():
            attempts["n"] += 1
            raise ValueError("nope")

        with patch("src.utils.retry.time.sleep"):
            with self.assertRaises(ValueError):
                bad()
        self.assertEqual(attempts["n"], 1)

    def test_raises_after_max_attempts_on_retryable_error(self):
        attempts = {"n": 0}

        @with_retry(max_attempts=2, base_delay=0)
        def always_timeout():
            attempts["n"] += 1
            raise requests.Timeout("slow")

        with patch("src.utils.retry.time.sleep"):
            with self.assertRaises(requests.Timeout):
                always_timeout()
        self.assertEqual(attempts["n"], 2)

    def test_http_error_status_controls_retryability(self):
        attempts = {"n": 0}

        @with_retry(max_attempts=3, base_delay=0)
        def not_found():
            attempts["n"] += 1
            exc = requests.HTTPError("404")
            response = requests.Response()
            response.status_code = 404
            exc.response = response
            raise exc

        with patch("src.utils.retry.time.sleep"):
            with self.assertRaises(requests.HTTPError):
                not_found()
        self.assertEqual(attempts["n"], 1)

    def test_logger_invoked_between_attempts(self):
        messages = []
        attempts = {"n": 0}

        @with_retry(max_attempts=2, base_delay=0, logger=messages.append)
        def flaky():
            attempts["n"] += 1
            raise requests.ConnectionError("boom")

        with patch("src.utils.retry.time.sleep"):
            with self.assertRaises(requests.ConnectionError):
                flaky()
        self.assertEqual(len(messages), 1)
        self.assertIn("retry", messages[0])


if __name__ == "__main__":
    unittest.main()
