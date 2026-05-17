import unittest
from datetime import UTC, datetime, timedelta, timezone  # pyright: ignore[reportUnusedImport]
from unittest.mock import MagicMock, patch

from src.agents.ci_health.agent import CIHealthAgent
from src.agents.pr_sla.agent import PRSLAAgent
from src.notifications.telegram import TelegramNotifier


class TestAgentsCoverage(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock()
        self.github_client = MagicMock()
        self.allowlist = MagicMock()
        self.allowlist.list_repositories.return_value = ["owner/repo"]
        self.allowlist.is_allowed.return_value = True
        self.telegram = MagicMock(spec=TelegramNotifier)
        self.telegram.escape = TelegramNotifier.escape
        self.telegram.escape_html = TelegramNotifier.escape_html

    def test_ci_health_agent(self):
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")
        self.assertFalse(agent.uses_repository_allowlist())

        # Test escape through telegram
        self.assertEqual(agent.telegram.escape("hello_world"), "hello\\_world")
        self.assertEqual(agent.telegram.escape(None), "")

        # Test persona/mission
        with patch.object(agent, "get_instructions_section") as mock_instr:
            mock_instr.return_value = "Content"
            self.assertEqual(agent.persona, "Content")
            self.assertEqual(agent.mission, "Content")

        # Test run with failures
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.owner.login = "testuser"
        mock_repo.private = False
        self.github_client.get_repo.return_value = mock_repo
        mock_user = MagicMock()
        mock_user.get_repos.return_value = [mock_repo]
        self.github_client.g.get_user.return_value = mock_user
        # Set up rate limit mock to avoid TypeError
        rate_limit_mock = MagicMock()
        rate_limit_mock.rate.remaining = 5000
        rate_limit_mock.rate.limit = 5000
        self.github_client.g.get_rate_limit.return_value = rate_limit_mock

        mock_run = MagicMock()
        mock_run.created_at = datetime.now(UTC)
        mock_run.conclusion = "failure"
        mock_run.name = "test-workflow"
        mock_run.head_branch = "main"
        mock_run.html_url = "http://url"

        mock_old_run = MagicMock()
        mock_old_run.created_at = datetime.now(UTC) - timedelta(hours=25)

        mock_repo.get_workflow_runs.return_value = [mock_run, mock_old_run]
        self.github_client.get_user_repos.return_value = [mock_repo]

        result = agent.run()
        self.assertEqual(result["count"], 1)
        self.assertGreaterEqual(self.telegram.send_message.call_count, 1)
        # Verify the final summary message was sent
        last_call_msg = self.telegram.send_message.call_args_list[-1][0][0]
        self.assertIn("CI HEALTH AGENT", last_call_msg)

        # Test run with exception
        self.github_client.get_repo.side_effect = Exception("Error")
        result = agent.run()
        self.assertEqual(result["count"], 0)
        self.github_client.get_repo.side_effect = None
        self.github_client.get_repo.return_value = mock_repo




    def test_pr_sla_agent(self):
        agent = PRSLAAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")

        # Test persona/mission/escape explicit
        with patch.object(agent, "get_instructions_section") as mock_instr:
            mock_instr.return_value = "Content"
            self.assertEqual(agent.persona, "Content")
            self.assertEqual(agent.mission, "Content")
        self.assertEqual(agent.telegram.escape(None), "")

        # Test run
        mock_issue = MagicMock()
        mock_pr = MagicMock()
        mock_pr.updated_at = datetime.now(UTC) - timedelta(hours=25)
        mock_pr.created_at = datetime.now(UTC) - timedelta(hours=25)
        mock_pr.base.repo.full_name = "owner/repo"
        mock_pr.number = 1
        mock_pr.title = "Stale PR"
        mock_pr.html_url = "http://url"

        self.github_client.search_prs.return_value = [mock_issue]
        self.github_client.get_pr_from_issue.return_value = mock_pr

        result = agent.run()
        self.assertEqual(result["count"], 1)

        # Test exception
        self.github_client.get_pr_from_issue.side_effect = Exception("Error")
        result = agent.run()
        self.assertEqual(result["count"], 0)



    def test_ci_health_agent_count_break(self):
        from src.agents.ci_health.agent import CIHealthAgent
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.owner.login = "testuser"
        mock_repo.private = False
        self.github_client.get_repo.return_value = mock_repo
        self.github_client.get_user_repos.return_value = [mock_repo]
        rate_limit_mock = MagicMock()
        rate_limit_mock.rate.remaining = 5000
        rate_limit_mock.rate.limit = 5000
        self.github_client.g.get_rate_limit.return_value = rate_limit_mock

        mock_run = MagicMock()
        mock_run.created_at = datetime.now(UTC)
        mock_run.conclusion = "failure"
        mock_run.name = "test-workflow"
        mock_run.head_branch = "main"
        mock_run.html_url = "http://url"

        mock_repo.get_workflow_runs.return_value = [mock_run] * 35
        result = agent.run()
        self.assertEqual(result["count"], 30)
