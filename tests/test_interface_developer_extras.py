
import unittest
from unittest.mock import MagicMock, patch

from src.agents.interface_developer.agent import InterfaceDeveloperAgent


class TestInterfaceDeveloperExtras(unittest.TestCase):
    def setUp(self):
        self.agent = InterfaceDeveloperAgent(MagicMock(), MagicMock(), MagicMock())
        self.agent.github_client = MagicMock()

    def test_analyze_ui_needs_no_repo_info_final(self):
        self.agent.get_repository_info = MagicMock(return_value=None)
        res = self.agent.analyze_ui_needs("repo")
        self.assertFalse(res["has_ui_work"])

    def test_analyze_ui_needs_design_exists_final(self):
        mock_repo = MagicMock()
        mock_repo.language = "JavaScript"
        mock_repo.get_issues.return_value = []
        mock_repo.get_contents.return_value = "content"
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        res = self.agent.analyze_ui_needs("repo")
        self.assertEqual(len(res["improvements"]), 0)

    def test_run_empty_allowlist_fix(self):
        self.agent.get_allowed_repositories = MagicMock(return_value=[])
        self.agent.log = MagicMock()
        res = self.agent.run()
        self.assertEqual(res["status"], "skipped")
        self.agent.log.assert_any_call("No repositories in allowlist. Nothing to do.", "WARNING")

    def test_run_no_ui_work_and_exception_fix(self):
        self.agent.get_allowed_repositories = MagicMock(return_value=["repo1", "repo2"])
        self.agent.log = MagicMock()

        def mock_analyze(r):
            if r == "repo1":
                return {"has_ui_work": False}
            raise Exception("API Error")

        self.agent.analyze_ui_needs = MagicMock(side_effect=mock_analyze)
        res = self.agent.run()

        self.agent.log.assert_any_call("No UI work needed for repo1")
        self.agent.log.assert_any_call("Failed to process repo2: API Error", "ERROR")
        self.assertEqual(res["failed"][0]["error"], "API Error")
