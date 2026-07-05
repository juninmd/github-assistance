import os
import unittest
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

from src.agents.senior_developer.utils import (
    count_today_sessions_utc_minus_3,
    create_burst_task,
    execute_burst_action,
    is_same_day,
    run_end_of_day_session_burst,
)


class TestSeniorDeveloperUtilsCoverage(unittest.TestCase):
    def test_is_same_day(self):
        # Test valid createTime
        session = {"createTime": "2026-07-03T10:00:00Z"}
        target = date(2026, 7, 3)
        # Note: 2026-07-03T10:00:00Z - 3 hours is 07:00:00, which is same day
        self.assertTrue(is_same_day(session, target))

        # Test valid createdAt
        session2 = {"createdAt": "2026-07-03T02:00:00Z"}
        # 2026-07-03T02:00:00Z - 3 hours is 2026-07-02T23:00:00, different day
        self.assertFalse(is_same_day(session2, target))

        # Test datetime target
        target_dt = datetime(2026, 7, 3, 12, 0, 0, tzinfo=UTC)
        self.assertTrue(is_same_day(session, target_dt))

        # Test invalid iso format
        session_invalid = {"createTime": "invalid-format"}
        self.assertFalse(is_same_day(session_invalid, target))

        # Test missing time key
        self.assertFalse(is_same_day({}, target))

    def test_count_today_sessions_utc_minus_3(self):
        jules_client = MagicMock()
        log_func = MagicMock()

        # Mock sessions returned from list_sessions
        # One matching today (UTC-3), one matching yesterday, one invalid
        now_dt = datetime.now(UTC)
        matching_session = {"createTime": now_dt.isoformat()}
        yesterday_session = {"createTime": "1999-01-01T12:00:00Z"}
        invalid_session = {"createTime": "invalid"}

        jules_client.list_sessions.return_value = [
            matching_session,
            yesterday_session,
            invalid_session,
        ]

        count = count_today_sessions_utc_minus_3(jules_client, log_func)
        self.assertEqual(count, 1)

        # Test listing sessions exception
        jules_client.list_sessions.side_effect = Exception("API error")
        count_err = count_today_sessions_utc_minus_3(jules_client, log_func)
        self.assertEqual(count_err, 0)
        log_func.assert_called_with("Failed to list session quota: API error", "WARNING")

    def test_create_burst_task_no_findings(self):
        analyzer = MagicMock()
        task_creator = MagicMock()
        log_func = MagicMock()

        # Mock analyze method to return empty/no findings
        analyzer.analyze_security = MagicMock()
        analyzer.analyze_security.__name__ = "analyze_security"
        analyzer.analyze_security.return_value = {"needs_attention": False}

        result = create_burst_task("my-repo", 0, analyzer, task_creator, log_func)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "no_findings")
        log_func.assert_called_once()

    def test_create_burst_task_success(self):
        analyzer = MagicMock()
        task_creator = MagicMock()
        log_func = MagicMock()

        # Mock analyze method to return actionable findings
        analyzer.analyze_security = MagicMock()
        analyzer.analyze_security.__name__ = "analyze_security"
        analyzer.analyze_security.return_value = {"needs_attention": True}

        task_creator.create_security_task = MagicMock()
        task_creator.create_security_task.__name__ = "create_security_task"
        task_creator.create_security_task.return_value = {"id": "session-123"}

        result = create_burst_task("my-repo", 0, analyzer, task_creator, log_func)
        self.assertEqual(result["session_id"], "session-123")
        self.assertEqual(result["task_type"], "create_security_task")

    def test_execute_burst_action_success(self):
        analyzer = MagicMock()
        task_creator = MagicMock()
        log_func = MagicMock()

        analyzer.analyze_security = MagicMock()
        analyzer.analyze_security.__name__ = "analyze_security"
        analyzer.analyze_security.return_value = {"needs_attention": True}

        task_creator.create_security_task = MagicMock()
        task_creator.create_security_task.__name__ = "create_security_task"
        task_creator.create_security_task.return_value = {"id": "session-123"}

        res = execute_burst_action(["repoA"], 0, analyzer, task_creator, log_func)
        self.assertEqual(res["session_id"], "session-123")

    def test_execute_burst_action_exception(self):
        analyzer = MagicMock()
        task_creator = MagicMock()
        log_func = MagicMock()

        analyzer.analyze_security = MagicMock()
        analyzer.analyze_security.__name__ = "analyze_security"
        analyzer.analyze_security.side_effect = Exception("analysis failed")

        res = execute_burst_action(["repoA"], 0, analyzer, task_creator, log_func)
        self.assertEqual(res["error"], "analysis failed")

    @patch("src.agents.senior_developer.utils.count_today_sessions_utc_minus_3")
    def test_run_end_of_day_session_burst_conditions(self, mock_count):
        jules_client = MagicMock()
        analyzer = MagicMock()
        task_creator = MagicMock()
        log_func = MagicMock()

        # Test early return if max_actions <= 0
        with patch.dict(os.environ, {"JULES_BURST_MAX_ACTIONS": "0"}):
            self.assertEqual(run_end_of_day_session_burst(["repo"], jules_client, analyzer, task_creator, log_func), [])

        # Test early return if triggers hour is not met
        # Suppose trigger hour is 18 (UTC-3), we set current UTC time to 13:00 (which is 10:00 UTC-3)
        class MockDatetime10(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 7, 3, 13, 0, 0, tzinfo=UTC)

        with patch.dict(os.environ, {"JULES_BURST_MAX_ACTIONS": "5", "JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3": "18"}):
            with patch("src.agents.senior_developer.utils.datetime", MockDatetime10):
                self.assertEqual(run_end_of_day_session_burst(["repo"], jules_client, analyzer, task_creator, log_func), [])

        # Test executing burst actions
        # Current hour 22:00 UTC (19:00 UTC-3), trigger hour 18, limit 100, count 98 (2 actions remaining, but max actions is 5, so we run 2)
        mock_count.return_value = 98

        analyzer.analyze_security = MagicMock()
        analyzer.analyze_security.__name__ = "analyze_security"
        analyzer.analyze_security.return_value = {"needs_attention": True}

        task_creator.create_security_task = MagicMock()
        task_creator.create_security_task.__name__ = "create_security_task"
        task_creator.create_security_task.return_value = {"id": "session-123"}

        class MockDatetime19(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 7, 3, 22, 0, 0, tzinfo=UTC)

        with patch.dict(os.environ, {
            "JULES_BURST_MAX_ACTIONS": "5",
            "JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3": "18",
            "JULES_DAILY_SESSION_LIMIT": "100"
        }):
            with patch("src.agents.senior_developer.utils.datetime", MockDatetime19):
                res = run_end_of_day_session_burst(["repo"], jules_client, analyzer, task_creator, log_func)
                self.assertEqual(len(res), 2)
