
import os
import unittest
from unittest.mock import MagicMock, patch

from src.agents.jules_tracker.agent import JulesTrackerAgent


class TestJulesTrackerAgentCoverage(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock()
        self.github_client = MagicMock()
        self.allowlist = MagicMock()
        self.allowlist.list_repositories.return_value = ["owner/repo"]
        self.allowlist.is_allowed.return_value = True
        self.telegram = MagicMock()
        self.telegram.escape = lambda x: str(x)

        with patch("src.agents.jules_tracker.agent.get_ai_client", return_value=MagicMock()):
            self.agent = JulesTrackerAgent(
                self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser"
            )
        self.agent.ai_client = MagicMock()

    def test_extract_repository_name_no_prefix(self):
        session = {"sourceContext": {"source": "owner/repo"}}
        from src.agents.jules_tracker import utils
        self.assertEqual(utils.extract_repository_name(session), "owner/repo")

    def test_get_pending_question_status_message(self):
        session = {"state": "AWAITING_USER_FEEDBACK", "statusMessage": "Need input"}
        from src.agents.jules_tracker import utils
        self.assertEqual(utils.get_pending_question(session, []), "Need input")

    def test_get_pending_question_status_message_without_state(self):
        session = {"status": "AWAITING_USER_FEEDBACK", "statusMessage": "Need input"}
        from src.agents.jules_tracker import utils
        self.assertEqual(utils.get_pending_question(session, []), "Need input")

    def test_colorize_with_env_var(self):
        with patch.dict("os.environ", {"NO_COLOR": "1"}):
            from src.agents.jules_tracker import utils
            self.assertEqual(utils.colorize("test", self.agent.QUESTION_COLOR), "test")

    def test_run_list_sessions_exception(self):
        self.jules_client.list_sessions.side_effect = Exception("API Error")
        result = self.agent.run()
        self.assertEqual(len(result["failed"]), 1)
        self.assertIn("API Error", result["failed"][0]["error"])

    def test_run_session_no_id(self):
        self.jules_client.list_sessions.return_value = [{"state": "IN_PROGRESS"}]
        result = self.agent.run()
        self.assertEqual(len(result["answered_questions"]), 0)

    def test_run_session_not_in_allowlist(self):
        self.agent.uses_repository_allowlist = MagicMock(return_value=True)
        self.agent.get_allowed_repositories = MagicMock(return_value=["owner/repo"])
        self.jules_client.list_sessions.return_value = [{"id": "1", "state": "IN_PROGRESS"}]
        with patch("src.agents.jules_tracker.utils.extract_repository_name", return_value="other/repo"):
            result = self.agent.run()
            self.assertEqual(len(result["answered_questions"]), 0)

    def test_run_process_session_exception(self):
        self.agent.uses_repository_allowlist = MagicMock(return_value=False)
        self.jules_client.list_sessions.return_value = [{"id": "1", "state": "IN_PROGRESS"}]
        with patch("src.agents.jules_tracker.utils.extract_repository_name", return_value="owner/repo"):
            self.jules_client.list_activities.side_effect = Exception("Activity Error")
            result = self.agent.run()
            self.assertEqual(len(result["failed"]), 1)
            self.assertIn("Activity Error", result["failed"][0]["error"])

    def test_run_session_with_url(self):
        self.agent.uses_repository_allowlist = MagicMock(return_value=False)
        self.jules_client.list_sessions.return_value = [{"id": "1", "state": "IN_PROGRESS", "url": "http://session"}]
        with patch("src.agents.jules_tracker.utils.extract_repository_name", return_value="owner/repo"):
            with patch("src.agents.jules_tracker.utils.get_pending_question", return_value="question"):
                self.jules_client.list_activities.return_value = []
                self.agent.ai_client.generate.return_value = "answer"
                result = self.agent.run()
                self.assertEqual(len(result["answered_questions"]), 1)
                self.assertEqual(result["answered_questions"][0]["session_url"], "http://session")

    def test_run_session_no_url(self):
        self.agent.uses_repository_allowlist = MagicMock(return_value=False)
        self.jules_client.list_sessions.return_value = [{"id": "1", "state": "IN_PROGRESS"}]
        with patch("src.agents.jules_tracker.utils.extract_repository_name", return_value="owner/repo"):
            with patch("src.agents.jules_tracker.utils.get_pending_question", return_value="question"):
                self.jules_client.list_activities.return_value = []
                self.agent.ai_client.generate.return_value = "answer"
                result = self.agent.run()
                self.assertEqual(len(result["answered_questions"]), 1)
                self.assertEqual(result["answered_questions"][0]["session_url"], "URL not provided by Jules API")

    def test_run_allowlist_match(self):
        self.agent.uses_repository_allowlist = MagicMock(return_value=True)
        self.agent.get_allowed_repositories = MagicMock(return_value=["owner/repo", "other/repo"])
        self.jules_client.list_sessions.return_value = [{"id": "1", "state": "IN_PROGRESS"}]
        with patch("src.agents.jules_tracker.utils.extract_repository_name", return_value="owner/repo"):
            with patch("src.agents.jules_tracker.utils.get_pending_question", return_value="question"):
                self.jules_client.list_activities.return_value = []
                self.agent.ai_client.generate.return_value = "answer"
                result = self.agent.run()
                self.assertEqual(len(result["answered_questions"]), 1)

    def test_persona_mission(self):
        with patch.object(self.agent, "get_instructions_section", return_value="Content"):
            self.assertEqual(self.agent.persona, "Content")
            self.assertEqual(self.agent.mission, "Content")

    def test_extract_repository_name_with_prefix(self):
        session = {"sourceContext": {"source": "sources/github/owner/repo"}}
        from src.agents.jules_tracker import utils
        self.assertEqual(utils.extract_repository_name(session), "owner/repo")

    def test_get_pending_question_with_activities(self):
        activities = [
            {"createTime": "2023-10-01T10:00:00Z", "agentMessaged": {"agentMessage": "first q"}},
            {"createTime": "2023-10-01T10:05:00Z", "userMessaged": {"text": "answer"}},
            {"createTime": "2023-10-01T10:10:00Z", "agentMessaged": {"agentMessage": "second q"}},
        ]
        from src.agents.jules_tracker import utils
        self.assertEqual(utils.get_pending_question({}, activities), "second q")

    def test_get_pending_question_all_answered(self):
        activities = [
            {"createTime": "2023-10-01T10:00:00Z", "agentMessaged": {"agentMessage": "first q"}},
            {"createTime": "2023-10-01T10:05:00Z", "userMessaged": {"text": "answer"}},
        ]
        from src.agents.jules_tracker import utils
        self.assertIsNone(utils.get_pending_question({}, activities))

    def test_run_empty_allowlist_when_enabled(self):
        self.agent.uses_repository_allowlist = MagicMock(return_value=True)
        self.agent.get_allowed_repositories = MagicMock(return_value=[])
        result = self.agent.run()
        self.assertEqual(result["status"], "skipped")

    def test_colorize_without_env_var(self):
        with patch.dict("os.environ", {}, clear=True):
            from src.agents.jules_tracker import utils
            result = utils.colorize("test", self.agent.QUESTION_COLOR)
            self.assertTrue(result.startswith(self.agent.QUESTION_COLOR))
            self.assertTrue(result.endswith(self.agent.RESET_COLOR))

    def test_run_session_missing_id(self):
        self.agent.uses_repository_allowlist = MagicMock(return_value=False)
        self.jules_client.list_sessions.return_value = [{"state": "IN_PROGRESS"}]
        result = self.agent.run()
        self.assertEqual(len(result["answered_questions"]), 0)

    def test_run_session_with_activities_but_no_question(self):
        self.agent.uses_repository_allowlist = MagicMock(return_value=False)
        self.jules_client.list_sessions.return_value = [{"id": "1", "state": "IN_PROGRESS"}]
        with patch("src.agents.jules_tracker.utils.extract_repository_name", return_value="owner/repo"):
            with patch("src.agents.jules_tracker.utils.get_pending_question", return_value=None):
                self.jules_client.list_activities.return_value = []
                result = self.agent.run()
                self.assertEqual(len(result["answered_questions"]), 0)
