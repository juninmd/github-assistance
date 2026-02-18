import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from src.agents.senior_developer.agent import SeniorDeveloperAgent
import os

class TestSeniorDeveloperEdgeCases(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.agent = SeniorDeveloperAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist
        )

    @patch.dict(os.environ, {"JULES_BURST_MAX_ACTIONS": "5", "JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3": "18"})
    def test_burst_outside_window(self):
        # Mock time to be 10:00 UTC (07:00 UTC-3) -> Should be < 18
        with patch("src.agents.senior_developer.agent.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat

            repositories = ["repo1"]
            result = self.agent.run_end_of_day_session_burst(repositories)
            self.assertEqual(result, [])

    @patch.dict(os.environ, {"JULES_BURST_MAX_ACTIONS": "5", "JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3": "18", "JULES_DAILY_SESSION_LIMIT": "10"})
    def test_burst_no_sessions_remaining(self):
        # Mock time to be 22:00 UTC (19:00 UTC-3) -> Should be > 18
        with patch("src.agents.senior_developer.agent.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2023, 1, 1, 22, 0, 0, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat

            # Mock used sessions = 10 (limit)
            self.agent.jules_client.list_sessions.return_value = []
            with patch.object(self.agent, 'count_today_sessions_utc_minus_3', return_value=10):
                repositories = ["repo1"]
                result = self.agent.run_end_of_day_session_burst(repositories)
                self.assertEqual(result, [])

    @patch.dict(os.environ, {"JULES_BURST_MAX_ACTIONS": "5", "JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3": "18"})
    def test_burst_empty_repos(self):
        with patch("src.agents.senior_developer.agent.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2023, 1, 1, 22, 0, 0, tzinfo=timezone.utc)
            result = self.agent.run_end_of_day_session_burst([])
            self.assertEqual(result, [])

    @patch.dict(os.environ, {"JULES_BURST_MAX_ACTIONS": "5", "JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3": "18"})
    def test_burst_task_failure(self):
         with patch("src.agents.senior_developer.agent.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2023, 1, 1, 22, 0, 0, tzinfo=timezone.utc)

            with patch.object(self.agent, 'count_today_sessions_utc_minus_3', return_value=0):
                with patch.object(self.agent, 'create_burst_task', side_effect=Exception("Task Error")):
                    result = self.agent.run_end_of_day_session_burst(["repo1"])
                    self.assertEqual(len(result), 5)
                    self.assertIn("error", result[0])

    def test_count_sessions_exception(self):
        self.mock_jules.list_sessions.side_effect = Exception("API Error")
        count = self.agent.count_today_sessions_utc_minus_3()
        self.assertEqual(count, 0)

    def test_count_sessions_success(self):
        # Mock current time: 2023-01-01 12:00 UTC (09:00 UTC-3)
        with patch("src.agents.senior_developer.agent.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat

            # Sessions:
            # 1. Today (UTC-3): 2023-01-01 10:00 UTC (07:00 UTC-3) -> Count
            # 2. Yesterday (UTC-3): 2022-12-31 20:00 UTC (17:00 UTC-3) -> No Count
            # 3. Invalid -> No Count
            self.mock_jules.list_sessions.return_value = [
                {"createTime": "2023-01-01T10:00:00Z"},
                {"createTime": "2022-12-31T20:00:00Z"},
                {"createTime": None}
            ]

            count = self.agent.count_today_sessions_utc_minus_3()
            self.assertEqual(count, 1)

    def test_create_burst_task_success(self):
        # Test create_burst_task logic directly
        with patch.object(self.agent, 'create_security_task') as mock_sec:
            mock_sec.return_value = {"id": "sec1"}
            mock_sec.__name__ = "create_security_task"
            # idx=0 -> create_security_task
            task = self.agent.create_burst_task("repo1", 0)
            self.assertEqual(task["task_type"], "create_security_task")
            self.assertEqual(task["session_id"], "sec1")

        with patch.object(self.agent, 'create_cicd_task') as mock_cicd:
            mock_cicd.return_value = {"id": "cicd1"}
            mock_cicd.__name__ = "create_cicd_task"
            # idx=1 -> create_cicd_task
            task = self.agent.create_burst_task("repo1", 1)
            self.assertEqual(task["task_type"], "create_cicd_task")

    def test_extract_session_datetime(self):
        # Valid
        dt = self.agent.extract_session_datetime({"createTime": "2023-01-01T10:00:00Z"})
        self.assertIsNotNone(dt)

        # Missing
        dt = self.agent.extract_session_datetime({})
        self.assertIsNone(dt)

        # Invalid format
        dt = self.agent.extract_session_datetime({"createTime": "invalid"})
        self.assertIsNone(dt)

    def test_analyze_tech_debt_exception(self):
        self.mock_github.get_repo.side_effect = Exception("Repo Error")
        # analyze_tech_debt calls get_repository_info which catches exception and returns None
        # But if get_repository_info returns None, analyze_tech_debt returns clean dict.

        # We want to test exception INSIDE analyze_tech_debt block
        mock_repo = MagicMock()
        mock_repo.get_git_tree.side_effect = Exception("Tree Error")
        self.mock_github.get_repo.return_value = mock_repo

        result = self.agent.analyze_tech_debt("repo")
        self.assertFalse(result["needs_attention"])

    def test_analyze_modernization_exception(self):
        mock_repo = MagicMock()
        mock_repo.get_git_tree.side_effect = Exception("Tree Error")
        self.mock_github.get_repo.return_value = mock_repo

        result = self.agent.analyze_modernization("repo")
        self.assertFalse(result["needs_modernization"])

    def test_analyze_performance_exception(self):
        mock_repo = MagicMock()
        mock_repo.get_contents.side_effect = Exception("Contents Error")
        self.mock_github.get_repo.return_value = mock_repo

        result = self.agent.analyze_performance("repo")
        self.assertFalse(result["needs_optimization"])

    def test_persona_mission(self):
        # Just to cover the properties
        with patch.object(self.agent, 'get_instructions_section', return_value="Test"):
            self.assertEqual(self.agent.persona, "Test")
            self.assertEqual(self.agent.mission, "Test")

if __name__ == '__main__':
    unittest.main()
