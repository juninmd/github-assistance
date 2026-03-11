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
        self.assertFalse(agent.uses_repository_allowlist())
        mock_get_ai_client.assert_called_once_with(
            provider="gemini", model="gemini-2.5-flash"
        )

    @patch("src.agents.jules_tracker.agent.get_ai_client")
    def test_run_empty_allowlist(self, mock_get_ai_client):
        self.allowlist.list_repositories.return_value = []
        self.jules_client.list_sessions.return_value = []
        agent = JulesTrackerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            self.telegram,
        )
        result = agent.run()
        self.assertEqual(result["answered_questions"], [])
        self.assertEqual(result["failed"], [])

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
                "name": "sessions/session_123",
                "id": "session_123",
                "state": "AWAITING_USER_FEEDBACK",
                "sourceContext": {"source": "sources/github/owner/repo1"},
                "statusMessage": "Need more info"
            },
            {
                "id": "session_456",
                "state": "IN_PROGRESS",
                "sourceContext": {"source": "sources/github/owner/repo2"},
            }
        ]

        # list_activities mock for the first session
        self.jules_client.list_activities.return_value = [
            {
                "createTime": "2026-03-10T10:00:00Z",
                "agentMessaged": {
                    "agentMessage": "Old question"
                }
            },
            {
                "createTime": "2026-03-10T10:01:00Z",
                "userMessaged": {
                    "userMessage": "Already answered"
                }
            },
            {
                "createTime": "2026-03-10T10:02:00Z",
                "agentMessaged": {
                    "agentMessage": "What is the variable name?"
                }
            }
        ]

        # Call get_instructions_section to trigger coverage on abstract methods
        # inherited from BaseAgent without mocking them here

        result = agent.run()

        self.assertEqual(len(result["answered_questions"]), 2)
        self.assertEqual(result["answered_questions"][0]["session_id"], "session_123")
        self.assertEqual(result["answered_questions"][0]["repository"], "owner/repo1")
        self.assertEqual(result["answered_questions"][0]["answer"], "Proceed with your best judgement.")
        self.assertIn("question_description", result["answered_questions"][0])
        self.assertEqual(result["answered_questions"][1]["session_id"], "session_456")
        self.assertEqual(result["answered_questions"][1]["repository"], "owner/repo2")

        self.assertEqual(mock_ai_instance.generate.call_count, 2)
        self.assertEqual(self.jules_client.send_message.call_count, 2)
        self.telegram.send_message.assert_called()
        telegram_message = self.telegram.send_message.call_args_list[0].args[0]
        self.assertIn("Pergunta do Jules", telegram_message)
        self.assertIn("Resposta do LLM", telegram_message)
        self.assertIn("Sessao Jules", telegram_message)

    @patch("src.agents.jules_tracker.agent.get_ai_client")
    def test_run_skips_already_answered_question(self, mock_get_ai_client):
        agent = JulesTrackerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            self.telegram,
        )

        self.jules_client.list_sessions.return_value = [
            {
                "id": "session_123",
                "state": "IN_PROGRESS",
                "sourceContext": {"source": "sources/github/owner/repo1"},
            }
        ]
        self.jules_client.list_activities.return_value = [
            {
                "createTime": "2026-03-10T10:00:00Z",
                "agentMessaged": {
                    "agentMessage": "Need confirmation"
                }
            },
            {
                "createTime": "2026-03-10T10:01:00Z",
                "userMessaged": {
                    "userMessage": "Confirmed"
                }
            }
        ]

        result = agent.run()

        self.assertEqual(result["answered_questions"], [])
        self.jules_client.send_message.assert_not_called()

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
                "state": "AWAITING_USER_FEEDBACK",
                "sourceContext": {"source": "sources/github/owner/repo1"},
            },
            {
                "state": "AWAITING_USER_FEEDBACK", # missing id to cover line 74
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
                "state": "AWAITING_USER_FEEDBACK",
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
    def test_run_answers_question_without_allowlist_match(self, mock_get_ai_client):
        mock_ai_instance = MagicMock()
        mock_ai_instance.generate.return_value = "Use the default configuration."
        mock_get_ai_client.return_value = mock_ai_instance
        self.allowlist.list_repositories.return_value = []

        agent = JulesTrackerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            self.telegram,
        )

        self.jules_client.list_sessions.return_value = [
            {
                "id": "session_999",
                "state": "AWAITING_USER_FEEDBACK",
                "sourceContext": {"source": "sources/github/another-owner/repo-x"},
                "url": "https://jules.google/sessions/session_999",
            }
        ]
        self.jules_client.list_activities.return_value = [
            {
                "createTime": "2026-03-10T10:02:00Z",
                "agentMessaged": {
                    "agentMessage": "Can I proceed with the default configuration?"
                }
            }
        ]

        result = agent.run()

        self.assertEqual(len(result["answered_questions"]), 1)
        self.assertEqual(result["answered_questions"][0]["repository"], "another-owner/repo-x")
        self.jules_client.send_message.assert_called_once_with("session_999", "Use the default configuration.")

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
