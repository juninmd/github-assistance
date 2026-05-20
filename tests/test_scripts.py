import unittest
from unittest.mock import MagicMock, patch

from src.scripts import (
    all_agents,
    branch_cleaner,
    ci_health,
    code_reviewer,
    conflict_resolver,
    intelligence_standardizer,
    interface_developer,
    jules_tracker,
    pr_assistant,
    pr_sla,
    product_manager,
    project_creator,
    secret_remover,
    security_scanner,
    senior_developer,
)


class TestScripts(unittest.TestCase):
    def _assert_runs_agent(self, func, expected_name):
        with (
            patch("src.scripts.Settings.from_env") as mock_settings,
            patch("src.scripts.run_agent") as mock_run_agent,
        ):
            mock_settings.return_value = MagicMock()
            func()
            mock_run_agent.assert_called_once_with(expected_name, mock_settings.return_value)

    def test_product_manager(self):
        self._assert_runs_agent(product_manager, "product-manager")

    def test_interface_developer(self):
        self._assert_runs_agent(interface_developer, "interface-developer")

    def test_senior_developer(self):
        self._assert_runs_agent(senior_developer, "senior-developer")

    def test_pr_assistant(self):
        self._assert_runs_agent(pr_assistant, "pr-assistant")

    def test_security_scanner(self):
        self._assert_runs_agent(security_scanner, "security-scanner")

    def test_ci_health(self):
        self._assert_runs_agent(ci_health, "ci-health")

    def test_pr_sla(self):
        self._assert_runs_agent(pr_sla, "pr-sla")

    def test_jules_tracker(self):
        self._assert_runs_agent(jules_tracker, "jules-tracker")

    def test_secret_remover(self):
        self._assert_runs_agent(secret_remover, "secret-remover")

    def test_project_creator(self):
        self._assert_runs_agent(project_creator, "project-creator")

    def test_conflict_resolver(self):
        self._assert_runs_agent(conflict_resolver, "conflict-resolver")

    def test_code_reviewer(self):
        self._assert_runs_agent(code_reviewer, "code-reviewer")

    def test_branch_cleaner(self):
        self._assert_runs_agent(branch_cleaner, "branch-cleaner")

    def test_intelligence_standardizer(self):
        self._assert_runs_agent(intelligence_standardizer, "intelligence-standardizer")

    def test_all_agents(self):
        with (
            patch("src.scripts.Settings.from_env") as mock_settings,
            patch("src.scripts.run_all") as mock_run_all,
        ):
            mock_settings.return_value = MagicMock()
            all_agents()
            mock_run_all.assert_called_once_with(mock_settings.return_value)

    def test_settings_error_handling(self):
        with (
            patch("src.scripts.Settings.from_env") as mock_settings,
        ):
            mock_settings.side_effect = ValueError("Missing GITHUB_TOKEN")
            with self.assertRaises(ValueError):
                pr_assistant()
