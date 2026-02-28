import unittest
from unittest.mock import MagicMock, patch

from src.agents.interface_developer.agent import InterfaceDeveloperAgent


class TestInterfaceDeveloperCoverage(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.list_repositories.return_value = ["repo1"]
        self.agent = InterfaceDeveloperAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

    def test_run_empty_allowlist(self):
        self.mock_allowlist.list_repositories.return_value = []
        result = self.agent.run()
        self.assertEqual(result["status"], "skipped")

    def test_run_exception(self):
        with patch.object(self.agent, 'analyze_ui_needs', side_effect=Exception("Error")):
             result = self.agent.run()
             self.assertEqual(len(result["failed"]), 1)

    @patch.object(InterfaceDeveloperAgent, 'get_repository_info')
    def test_analyze_ui_needs_design_exists(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.language = "JavaScript"
        mock_repo.get_issues.return_value = []

        # DESIGN.md exists
        mock_repo.get_contents.return_value = MagicMock()

        result = self.agent.analyze_ui_needs("repo")
        # No issues, design exists -> no improvements
        self.assertFalse(result["has_ui_work"])
        self.assertEqual(len(result["improvements"]), 0)

    @patch.object(InterfaceDeveloperAgent, 'get_repository_info')
    def test_analyze_ui_needs_not_frontend(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.language = "C++"

        result = self.agent.analyze_ui_needs("repo")
        self.assertFalse(result["is_frontend_project"])
