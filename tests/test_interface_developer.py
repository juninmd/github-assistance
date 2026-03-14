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

        # Simulate missing DESIGN.md to trigger that improvement
        mock_repo.get_contents.side_effect = Exception("Not found")

        result = self.agent.analyze_ui_needs("juninmd/test-repo")

        self.assertTrue(result["has_ui_work"])
        self.assertTrue(result["is_frontend_project"])
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
        self.assertFalse(result["is_frontend_project"])

    @patch.object(InterfaceDeveloperAgent, 'get_repository_info')
    def test_analyze_ui_needs_access_failure(self, mock_get_repo):
        mock_get_repo.return_value = None

        result = self.agent.analyze_ui_needs("juninmd/test-repo")

        self.assertFalse(result["has_ui_work"])
        self.assertEqual(result["language"], "Unknown")

    @patch.object(InterfaceDeveloperAgent, 'create_jules_session')
    def test_create_ui_improvement_task(self, mock_create_session):
        mock_create_session.return_value = {"id": "session-123"}

        analysis = {
            "improvements": ["Fix header", "Add dark mode"],
            "language": "Vue"
        }

        with patch.object(self.agent, 'load_jules_instructions', return_value="Do UI work"):
            result = self.agent.create_ui_improvement_task("juninmd/test-repo", analysis)

            self.assertEqual(result["id"], "session-123")
            mock_create_session.assert_called_once()
            _args, kwargs = mock_create_session.call_args
            self.assertEqual(kwargs['repository'], "juninmd/test-repo")
            self.assertEqual(kwargs['title'], "UI Enhancement for juninmd/test-repo")

    @patch.object(InterfaceDeveloperAgent, 'analyze_ui_needs')
    @patch.object(InterfaceDeveloperAgent, 'create_ui_improvement_task')
    def test_run(self, mock_create_task, mock_analyze):
        mock_analyze.return_value = {
            "has_ui_work": True,
            "improvements": ["Imp 1"]
        }
        mock_create_task.return_value = {"id": "session-1"}

        results = self.agent.run()

        self.assertEqual(len(results["ui_tasks_created"]), 1)
        self.assertEqual(results["ui_tasks_created"][0]["session_id"], "session-1")

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
