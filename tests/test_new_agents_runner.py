import sys
import unittest
from unittest.mock import MagicMock, patch

from src.run_agent import main as run_agent_main


class TestNewAgentsRunner(unittest.TestCase):
    @patch("src.run_agent.CIHealthAgent")
    @patch("src.run_agent.Settings")
    @patch("src.run_agent.GithubClient")
    @patch("src.run_agent.JulesClient")
    @patch("src.run_agent.RepositoryAllowlist")
    def test_run_ci_health(self, _allowlist, _jules, _github, mock_settings, mock_agent):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent.return_value.run.return_value = {"status": "ok"}
        with patch.object(sys, "argv", ["run-agent", "ci-health"]):
            run_agent_main()
        mock_agent.assert_called_once()

    @patch("src.run_agent.ReleaseWatcherAgent")
    @patch("src.run_agent.Settings")
    @patch("src.run_agent.GithubClient")
    @patch("src.run_agent.JulesClient")
    @patch("src.run_agent.RepositoryAllowlist")
    def test_run_release_watcher(self, _allowlist, _jules, _github, mock_settings, mock_agent):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent.return_value.run.return_value = {"status": "ok"}
        with patch.object(sys, "argv", ["run-agent", "release-watcher"]):
            run_agent_main()
        mock_agent.assert_called_once()

    @patch("src.run_agent.DependencyRiskAgent")
    @patch("src.run_agent.Settings")
    @patch("src.run_agent.GithubClient")
    @patch("src.run_agent.JulesClient")
    @patch("src.run_agent.RepositoryAllowlist")
    def test_run_dependency_risk(self, _allowlist, _jules, _github, mock_settings, mock_agent):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent.return_value.run.return_value = {"status": "ok"}
        with patch.object(sys, "argv", ["run-agent", "dependency-risk"]):
            run_agent_main()
        mock_agent.assert_called_once()

    @patch("src.run_agent.PRSLAAgent")
    @patch("src.run_agent.Settings")
    @patch("src.run_agent.GithubClient")
    @patch("src.run_agent.JulesClient")
    @patch("src.run_agent.RepositoryAllowlist")
    def test_run_pr_sla(self, _allowlist, _jules, _github, mock_settings, mock_agent):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent.return_value.run.return_value = {"status": "ok"}
        with patch.object(sys, "argv", ["run-agent", "pr-sla"]):
            run_agent_main()
        mock_agent.assert_called_once()

    @patch("src.run_agent.IssueEscalationAgent")
    @patch("src.run_agent.Settings")
    @patch("src.run_agent.GithubClient")
    @patch("src.run_agent.JulesClient")
    @patch("src.run_agent.RepositoryAllowlist")
    def test_run_issue_escalation(self, _allowlist, _jules, _github, mock_settings, mock_agent):
        mock_settings.from_env.return_value = MagicMock()
        mock_agent.return_value.run.return_value = {"status": "ok"}
        with patch.object(sys, "argv", ["run-agent", "issue-escalation"]):
            run_agent_main()
        mock_agent.assert_called_once()
