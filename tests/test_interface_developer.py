import unittest
from unittest.mock import MagicMock, patch

from src.agents.interface_developer.agent import InterfaceDeveloperAgent


class TestInterfaceDeveloperAgent(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.list_repositories.return_value = ["juninmd/test-repo"]
        self.agent = InterfaceDeveloperAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

    def test_persona_and_mission(self):
        # Mock instructions loading
        with patch.object(self.agent, 'get_instructions_section', return_value="Test Content"):
            self.assertEqual(self.agent.persona, "Test Content")
            self.assertEqual(self.agent.mission, "Test Content")

    @patch.object(InterfaceDeveloperAgent, 'get_repository_info')
    def test_analyze_ui_needs_frontend_with_issues(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.language = "TypeScript"

        issue1 = MagicMock(title="Fix UI layout", body="The button is misaligned")
        issue2 = MagicMock(title="Backend error", body="500 error")
        mock_repo.get_issues.return_value = [issue1, issue2]

        mock_repo.get_contents.side_effect = Exception("Not found")

        result = self.agent.analyze_ui_needs("juninmd/test-repo")

        self.assertTrue(result["has_ui_work"])
        self.assertIn("Resolve UI issue: Fix UI layout", result["improvements"])
        self.assertIn("Create DESIGN.md with design system documentation", result["improvements"])

    @patch.object(InterfaceDeveloperAgent, 'get_repository_info')
    def test_analyze_ui_needs_backend(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.language = "Python"
        mock_repo.get_issues.return_value = []

        result = self.agent.analyze_ui_needs("juninmd/test-repo")

        self.assertFalse(result["has_ui_work"])

    @patch.object(InterfaceDeveloperAgent, 'get_repository_info')
    def test_analyze_ui_needs_access_failure(self, mock_get_repo):
        mock_get_repo.return_value = None

        result = self.agent.analyze_ui_needs("juninmd/test-repo")

        self.assertFalse(result["has_ui_work"])

    @patch.object(InterfaceDeveloperAgent, 'create_ui_improvement_issue')
    def test_create_ui_improvement_task(self, mock_create_issue):
        mock_create_issue.return_value = {"issue_url": "http://github.com/issue/1"}

        analysis = {
            "improvements": ["Fix header", "Add dark mode"],
            "repo_obj": MagicMock(),
        }

        result = self.agent.create_ui_improvement_issue("juninmd/test-repo", analysis)

        self.assertEqual(result["issue_url"], "http://github.com/issue/1")

    @patch.object(InterfaceDeveloperAgent, 'analyze_ui_needs')
    @patch.object(InterfaceDeveloperAgent, 'create_ui_improvement_issue')
    def test_run(self, mock_create_issue, mock_analyze):
        self.mock_allowlist.list_repositories.return_value = ["juninmd/test-repo"]
        mock_analyze.return_value = {
            "has_ui_work": True,
            "improvements": ["Imp 1"]
        }
        mock_create_issue.return_value = {"issue_url": "http://github.com/issue/1"}

        self.agent = InterfaceDeveloperAgent(
            self.mock_jules, self.mock_github, self.mock_allowlist,
            enforce_repository_allowlist=True,
        )
        self.agent.analyze_ui_needs = mock_analyze
        self.agent.create_ui_improvement_issue = mock_create_issue

        results = self.agent.run()

        self.assertEqual(len(results["ui_issues_created"]), 1)

if __name__ == '__main__':
    unittest.main()

    def test_analyze_ui_needs_design_md_exists(self):
        mock_repo = MagicMock()
        mock_repo.language = "JavaScript"
        mock_repo.get_issues.return_value = []
        mock_repo.get_contents.return_value = "design file"
        self.github_client.get_repo.return_value = mock_repo

        analysis = self.agent.analyze_ui_needs("owner/repo")
        self.assertEqual(len(analysis["improvements"]), 0)

    def test_run_empty_allowlist_real_cov(self):
        self.agent.get_allowed_repositories = MagicMock(return_value=[])
        self.agent.log = MagicMock()
        res = self.agent.run()
        self.assertEqual(res["status"], "skipped")
        self.agent.log.assert_any_call("No repositories in allowlist. Nothing to do.", "WARNING")

    def test_run_no_ui_work_and_exception(self):
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

    def test_analyze_ui_needs_none_real_8(self):
        self.agent.get_repository_info = MagicMock(return_value=None)
        res = self.agent.analyze_ui_needs("r")
        self.assertFalse(res["has_ui_work"])

    def test_analyze_ui_needs_design_md_real_8(self):
        mock_repo = MagicMock()
        mock_repo.language = "JavaScript"
        mock_repo.get_issues.return_value = []
        mock_repo.get_contents.return_value = "content"
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        res = self.agent.analyze_ui_needs("r")
        self.assertEqual(len(res["improvements"]), 0)


    def test_analyze_ui_needs_no_repo_info(self):
        self.agent.get_repository_info = MagicMock(return_value=None)
        res = self.agent.analyze_ui_needs("repo")
        self.assertFalse(res["has_ui_work"])

    def test_analyze_ui_needs_design_exists(self):
        mock_repo = MagicMock()
        mock_repo.language = "JavaScript"
        mock_repo.get_issues.return_value = []
        mock_repo.get_contents.return_value = "content"
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        res = self.agent.analyze_ui_needs("repo")
        self.assertEqual(len(res["improvements"]), 0)

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
if __name__ == "__main__":
    unittest.main()
