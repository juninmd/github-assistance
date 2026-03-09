import unittest
from datetime import UTC, datetime, timedelta, timezone  # pyright: ignore[reportUnusedImport]
from unittest.mock import MagicMock, patch

from src.agents.ci_health.agent import CIHealthAgent
from src.agents.dependency_risk.agent import DependencyRiskAgent
from src.agents.issue_escalation.agent import IssueEscalationAgent
from src.agents.pr_sla.agent import PRSLAAgent
from src.agents.release_watcher.agent import ReleaseWatcherAgent
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

    def test_ci_health_agent(self):
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")

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
        self.github_client.get_repo.return_value = mock_repo

        mock_run = MagicMock()
        mock_run.created_at = datetime.now(UTC)
        mock_run.conclusion = "failure"
        mock_run.name = "test-workflow"
        mock_run.head_branch = "main"
        mock_run.html_url = "http://url"

        mock_old_run = MagicMock()
        mock_old_run.created_at = datetime.now(UTC) - timedelta(hours=25)

        mock_repo.get_workflow_runs.return_value = [mock_run, mock_old_run]

        result = agent.run()
        self.assertEqual(result["count"], 1)
        self.telegram.send_message.assert_called_once()

        # Test run with exception
        self.github_client.get_repo.side_effect = Exception("Error")
        result = agent.run()
        self.assertEqual(result["count"], 0)

        # Test allowed_repositories fallback
        self.allowlist.list_repositories.return_value = []
        mock_user = MagicMock()
        mock_user.get_repos.return_value = [mock_repo]
        self.github_client.g.get_user.return_value = mock_user
        self.github_client.get_repo.side_effect = None
        self.github_client.get_repo.return_value = mock_repo

        agent.run()
        mock_user.get_repos.assert_called_once()

    def test_dependency_risk_agent(self):
        agent = DependencyRiskAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")

        # Test persona/mission/escape explicit
        with patch.object(agent, "get_instructions_section") as mock_instr:
            mock_instr.return_value = "Content"
            self.assertEqual(agent.persona, "Content")
            self.assertEqual(agent.mission, "Content")
        self.assertEqual(agent.telegram.escape(None), "")

        # Test _risk_level — new CVSS/severity/keyword logic
        self.assertEqual(agent._risk_level("Security fix", ""), "alto")           # HIGH_RISK_KEYWORDS
        self.assertEqual(agent._risk_level("Major update", ""), "medio")          # MEDIUM_RISK_KEYWORDS
        self.assertEqual(agent._risk_level("Minor update", ""), "baixo")          # no keyword match
        self.assertEqual(agent._risk_level("Fix typo", ""), "baixo")
        self.assertEqual(agent._risk_level("", "CVSS: 9.1"), "alto")             # CVSS score
        self.assertEqual(agent._risk_level("", "severity: critical"), "alto")     # severity label
        self.assertEqual(agent._risk_level("", "severity: low"), "baixo")         # severity label low
        self.assertEqual(agent._risk_level("CVE-2024-1234 fix", ""), "alto")      # CVE keyword

        # Test run
        mock_issue = MagicMock()
        mock_issue.number = 1

        mock_issue2 = MagicMock()
        mock_issue2.number = 2

        mock_pr = MagicMock()
        mock_pr.created_at = datetime.now(UTC)
        mock_pr.title = "Security fix"
        mock_pr.body = "CVE-123"
        mock_pr.number = 1
        mock_pr.html_url = "http://url"
        mock_pr.base.repo.full_name = "owner/repo"

        # since search_prs is called 4 times, we can return the items we want
        # the agent dedupes by issue.number
        self.github_client.search_prs.side_effect = [[mock_issue], [mock_issue2], [], []]

        mock_old_pr = MagicMock()
        mock_old_pr.created_at = datetime.now(UTC) - timedelta(days=20)

        self.github_client.get_pr_from_issue.side_effect = [mock_pr, mock_old_pr]

        result = agent.run()
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["pull_requests"][0]["risk"], "alto")
        self.github_client.get_pr_from_issue.side_effect = None
        self.github_client.search_prs.side_effect = None

        # Test exception
        self.github_client.get_pr_from_issue.side_effect = Exception("Error")
        result = agent.run()
        self.assertEqual(result["count"], 0)

    def test_issue_escalation_agent(self):
        agent = IssueEscalationAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")

        # Test persona/mission/escape explicit
        with patch.object(agent, "get_instructions_section") as mock_instr:
            mock_instr.return_value = "Content"
            self.assertEqual(agent.persona, "Content")
            self.assertEqual(agent.mission, "Content")
        self.assertEqual(agent.telegram.escape(None), "")

        # Test run
        mock_issue = MagicMock()
        mock_issue.updated_at = datetime.now(UTC) - timedelta(days=8)
        mock_issue.assignee = None # unassigned
        mock_issue.repository.full_name = "owner/repo"
        mock_issue.number = 1
        mock_issue.title = "Bug"
        mock_issue.html_url = "http://url"

        self.github_client.g.search_issues.return_value = [mock_issue]

        result = agent.run()
        self.assertEqual(result["count"], 1)

        # Test assigned but stale
        mock_issue.assignee = MagicMock()
        mock_issue.assignee.login = "dev"
        result = agent.run()
        self.assertEqual(result["count"], 1)

        # Test exception inside loop
        self.github_client.g.search_issues.side_effect = None
        self.github_client.g.search_issues.return_value = [mock_issue]

        bad_issue = MagicMock()
        type(bad_issue).assignee = unittest.mock.PropertyMock(side_effect=Exception("Error"))  # type: ignore
        self.github_client.g.search_issues.return_value = [bad_issue]

        result = agent.run()
        self.assertEqual(result["count"], 0)


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

    def test_release_watcher_agent(self):
        agent = ReleaseWatcherAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")

        # Test persona/mission/escape explicit
        with patch.object(agent, "get_instructions_section") as mock_instr:
            mock_instr.return_value = "Content"
            self.assertEqual(agent.persona, "Content")
            self.assertEqual(agent.mission, "Content")
        self.assertEqual(agent.telegram.escape(None), "")

        # Test run
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        self.github_client.get_repo.return_value = mock_repo

        mock_release = MagicMock()
        mock_release.created_at = datetime.now(UTC)
        mock_release.tag_name = "v1.0"
        mock_release.title = "Release 1.0"
        mock_release.html_url = "http://url"
        mock_release.draft = False
        mock_release.prerelease = False
        mock_repo.get_releases.return_value = [mock_release]

        result = agent.run()
        self.assertEqual(result["count"], 1)

        # Test break loop with old release
        mock_old_release = MagicMock()
        mock_old_release.created_at = datetime.now(UTC) - timedelta(days=8)
        mock_repo.get_releases.return_value = [mock_release, mock_old_release]
        result = agent.run()
        self.assertEqual(result["count"], 1)

        # Test exception inside loop
        self.github_client.get_repo.side_effect = Exception("Error")
        result = agent.run()
        self.assertEqual(result["count"], 0)
        self.github_client.get_repo.side_effect = None

        # Test fallback to user repos
        self.github_client.get_repo.return_value = mock_repo
        self.allowlist.list_repositories.return_value = []
        mock_user = MagicMock()
        mock_user.get_repos.return_value = [mock_repo]
        self.github_client.g.get_user.return_value = mock_user

        agent.run()
        mock_user.get_repos.assert_called_once()
