import unittest
from unittest.mock import MagicMock, patch

from src.agents.ci_health.agent import CIHealthAgent
from src.agents.ci_health.utils import create_issue_for_pipeline, remediate_pipeline
from src.config.settings import Settings


class TestCIHealthAgent(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock()
        self.github_client = MagicMock()
        self.allowlist = MagicMock()
        self.telegram = MagicMock()

    def setup_mock_repo(self):
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.private = False
        self.github_client.get_repo.return_value = mock_repo

        mock_user = MagicMock()
        mock_user.get_repos.return_value = [mock_repo]
        self.github_client.g.get_user.return_value = mock_user

        mock_run = MagicMock()
        from datetime import UTC, datetime
        mock_run.created_at = datetime.now(UTC)
        mock_run.conclusion = "failure"
        mock_run.name = "test-workflow"
        mock_run.head_branch = "main"
        mock_run.html_url = "http://url"

        mock_repo.get_workflow_runs.return_value = [mock_run]
        return mock_repo

    def setup_mock_repo(self):
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.private = False
        self.github_client.get_repo.return_value = mock_repo

        mock_user = MagicMock()
        mock_user.get_repos.return_value = [mock_repo]
        self.github_client.g.get_user.return_value = mock_user

        mock_run = MagicMock()
        from datetime import UTC, datetime
        mock_run.created_at = datetime.now(UTC)
        mock_run.conclusion = "failure"
        mock_run.name = "test-workflow"
        mock_run.head_branch = "main"
        mock_run.html_url = "http://url"

        mock_repo.get_workflow_runs.return_value = [mock_run]
        return mock_repo

    def setup_mock_repo(self):
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.private = False
        self.github_client.get_repo.return_value = mock_repo

        mock_user = MagicMock()
        mock_user.get_repos.return_value = [mock_repo]
        self.github_client.g.get_user.return_value = mock_user

        mock_run = MagicMock()
        from datetime import UTC, datetime
        mock_run.created_at = datetime.now(UTC)
        mock_run.conclusion = "failure"
        mock_run.name = "test-workflow"
        mock_run.head_branch = "main"
        mock_run.html_url = "http://url"

        mock_repo.get_workflow_runs.return_value = [mock_run]
        return mock_repo

    @patch('src.agents.ci_health.agent.remediate_pipeline')
    def test_run_remediation_success(self, mock_remediate):
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")
        self.setup_mock_repo()

        mock_remediate.return_value = {"repository": "owner/repo", "session_id": "123"}
        agent._allowed_repositories = MagicMock(return_value=["owner/repo"])
        agent.ai_provider = "mock"
        agent.ai_model = "mock"

        result = agent.run()
        self.assertEqual(len(result["fix_actions"]), 1)
        self.assertEqual(result["fix_actions"][0]["session_id"], "123")

    @patch('src.agents.ci_health.agent.remediate_pipeline')
    def test_run_remediation_issue(self, mock_remediate):
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")
        self.setup_mock_repo()

        mock_remediate.return_value = {"repository": "owner/repo", "issue_url": "http://issue"}
        agent._allowed_repositories = MagicMock(return_value=["owner/repo"])
        agent.ai_provider = "mock"
        agent.ai_model = "mock"

        result = agent.run()
        self.assertEqual(len(result["fix_actions"]), 1)
        self.assertEqual(result["fix_actions"][0]["issue_url"], "http://issue")

    @patch('src.agents.ci_health.agent.remediate_pipeline')
    def test_run_remediation_exception(self, mock_remediate):
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")
        self.setup_mock_repo()

        mock_remediate.side_effect = Exception("Test Exception")
        agent._allowed_repositories = MagicMock(return_value=["owner/repo"])
        agent.ai_provider = "mock"
        agent.ai_model = "mock"

        result = agent.run()
        self.assertEqual(len(result["fix_actions"]), 0)

    def test_create_issue_for_pipeline_no_ai(self):
        agent = MagicMock()
        agent._get_ai_client.return_value = None

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.html_url = "http://url"
        mock_repo.create_issue.return_value = mock_issue

        result = create_issue_for_pipeline(agent, mock_repo, "failures")
        self.assertEqual(result["issue_url"], "http://url")

    def test_create_issue_for_pipeline_with_ai(self):
        agent = MagicMock()
        mock_ai_client = MagicMock()
        mock_ai_client.generate.return_value = "AI issue body"
        agent._get_ai_client.return_value = mock_ai_client

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.html_url = "http://url"
        mock_repo.create_issue.return_value = mock_issue

        result = create_issue_for_pipeline(agent, mock_repo, "failures")
        self.assertEqual(result["issue_url"], "http://url")
        mock_repo.create_issue.assert_called_with(title="CI pipeline failing - please fix", body="AI issue body")

    def test_create_issue_for_pipeline_ai_exception(self):
        agent = MagicMock()
        mock_ai_client = MagicMock()
        mock_ai_client.generate.side_effect = Exception("AI Exception")
        agent._get_ai_client.return_value = mock_ai_client

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.html_url = "http://url"
        mock_repo.create_issue.return_value = mock_issue

        result = create_issue_for_pipeline(agent, mock_repo, "failures")
        self.assertEqual(result["issue_url"], "http://url")
        mock_repo.create_issue.assert_called_with(title="CI pipeline failing - please fix", body="CI pipeline failures:\nfailures")

    def test_create_issue_for_pipeline_create_exception(self):
        agent = MagicMock()
        agent._get_ai_client.return_value = None

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.create_issue.side_effect = Exception("GitHub Exception")

        result = create_issue_for_pipeline(agent, mock_repo, "failures")
        self.assertIsNone(result)

    def test_remediate_pipeline_recent_session(self):
        agent = MagicMock()
        agent.has_recent_jules_session.return_value = True

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"

        result = remediate_pipeline(agent, mock_repo, [])
        self.assertIsNone(result)

    def test_remediate_pipeline_success(self):
        agent = MagicMock()
        agent.has_recent_jules_session.return_value = False
        agent.load_jules_instructions.return_value = "Instructions"
        agent.create_jules_session.return_value = {"id": "123", "name": "session_name"}

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"

        failures = [{"name": "test", "conclusion": "failure", "url": "http://url"}]

        result = remediate_pipeline(agent, mock_repo, failures)
        self.assertEqual(result["session_id"], "123")
        self.assertEqual(result["session_name"], "session_name")

    @patch('src.agents.ci_health.utils.create_issue_for_pipeline')
    def test_remediate_pipeline_exception(self, mock_create_issue):
        agent = MagicMock()
        agent.has_recent_jules_session.return_value = False
        agent.load_jules_instructions.return_value = "Instructions"
        agent.create_jules_session.side_effect = Exception("Session Exception")

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"

        failures = [{"name": "test", "conclusion": "failure", "url": "http://url"}]

        mock_create_issue.return_value = {"issue_url": "http://issue"}

        result = remediate_pipeline(agent, mock_repo, failures)
        self.assertEqual(result["issue_url"], "http://issue")
