import unittest
from unittest.mock import MagicMock, patch

from src.agents.jules_tracker.agent import JulesTrackerAgent


class TestJulesTrackerAgent(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock()
        self.github_client = MagicMock()
        self.allowlist = MagicMock()
        self.allowlist.list_repositories.return_value = ["owner/repo1"]
        self.telegram = MagicMock()

    @patch("src.agents.jules_tracker.agent.get_ai_client")
    def test_init_default_ai(self, mock_get_ai_client):
        agent = JulesTrackerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            self.telegram,
        )
        self.assertEqual(agent.name, "jules_tracker")
        mock_get_ai_client.assert_called_once_with(
            provider="gemini", model="gemini-2.5-flash"
        )

    @patch("src.agents.jules_tracker.agent.get_ai_client")
    def test_run_empty_allowlist(self, mock_get_ai_client):
        self.allowlist.list_repositories.return_value = []
        agent = JulesTrackerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            self.telegram,
        )
        result = agent.run()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "empty_allowlist")

    @patch("src.agents.jules_tracker.agent.get_ai_client")
    def test_run_list_sessions_exception(self, mock_get_ai_client):
        agent = JulesTrackerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            self.telegram,
        )
        self.jules_client.list_sessions.side_effect = Exception("API error")
        result = agent.run()
        self.assertEqual(len(result["failed"]), 1)
        self.assertIn("API error", result["failed"][0]["error"])

    @patch("src.agents.jules_tracker.agent.get_ai_client")
    def test_run_answers_question(self, mock_get_ai_client):
        mock_ai_instance = MagicMock()
        mock_ai_instance.generate.return_value = "Proceed with your best judgement."
        mock_get_ai_client.return_value = mock_ai_instance

        agent = JulesTrackerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            self.telegram,
        )

        self.jules_client.list_sessions.return_value = [
            {
                "id": "session_123",
                "status": "WAITING_FOR_USER_INPUT",
                "sourceContext": {"source": "sources/github/owner/repo1"},
                "statusMessage": "Need more info"
            },
            {
                "id": "session_456",
                "status": "RUNNING",
                "sourceContext": {"source": "sources/github/owner/repo2"}, # Not allowed
            }
        ]

        # list_activities mock for the first session
        self.jules_client.list_activities.return_value = [
            {
                "type": "QUESTION",
                "text": "What is the variable name?"
            }
        ]

        # Call get_instructions_section to trigger coverage on abstract methods
        # inherited from BaseAgent without mocking them here

        result = agent.run()

        self.assertEqual(len(result["answered_questions"]), 1)
        self.assertEqual(result["answered_questions"][0]["session_id"], "session_123")
        self.assertEqual(result["answered_questions"][0]["repository"], "owner/repo1")
        self.assertEqual(result["answered_questions"][0]["answer"], "Proceed with your best judgement.")

        mock_ai_instance.generate.assert_called_once()
        self.jules_client.send_message.assert_called_once_with("session_123", "Proceed with your best judgement.")

    @patch("src.agents.jules_tracker.agent.get_ai_client")
    def test_run_no_activities(self, mock_get_ai_client):
        agent = JulesTrackerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            self.telegram,
        )

        self.jules_client.list_sessions.return_value = [
            {
                "id": "session_123",
                "status": "WAITING_FOR_USER_INPUT",
                "sourceContext": {"source": "sources/github/owner/repo1"},
            },
            {
                "status": "WAITING_FOR_USER_INPUT", # missing id to cover line 74
                "sourceContext": {"source": "sources/github/owner/repo1"},
            }
        ]

        # Empty activities
        self.jules_client.list_activities.return_value = []

        result = agent.run()

        self.assertEqual(len(result["answered_questions"]), 0)
        self.assertEqual(len(result["failed"]), 0)

    @patch("src.agents.jules_tracker.agent.get_ai_client")
    def test_run_process_session_exception(self, mock_get_ai_client):
        agent = JulesTrackerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            self.telegram,
        )

        self.jules_client.list_sessions.return_value = [
            {
                "id": "session_123",
                "status": "WAITING_FOR_USER_INPUT",
                "sourceContext": {"source": "sources/github/owner/repo1"},
            }
        ]

        self.jules_client.list_activities.side_effect = Exception("Activities failed")

        result = agent.run()

        self.assertEqual(len(result["answered_questions"]), 0)
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(result["failed"][0]["session_id"], "session_123")
        self.assertIn("Activities failed", result["failed"][0]["error"])

    @patch("src.agents.jules_tracker.agent.get_ai_client")
    @patch("src.agents.jules_tracker.agent.JulesTrackerAgent.get_instructions_section")
    def test_properties(self, mock_get_section, mock_get_ai_client):
        mock_get_section.side_effect = lambda x: "Mocked " + x
        agent = JulesTrackerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            self.telegram,
        )
        self.assertEqual(agent.persona, "Mocked ## Persona")
        self.assertEqual(agent.mission, "Mocked ## Mission")
        mock_get_section.assert_any_call("## Persona")
        mock_get_section.assert_any_call("## Mission")


if __name__ == "__main__":
    unittest.main()
