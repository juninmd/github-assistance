import unittest
from unittest.mock import MagicMock, patch
from src.agents.senior_developer.agent import SeniorDeveloperAgent
from src.agents.senior_developer.analyzers import SeniorDeveloperAnalyzer
from src.agents.senior_developer.task_creator import SeniorDeveloperTaskCreator
from github.GithubException import UnknownObjectException
import time
from datetime import datetime, UTC

class TestSeniorDeveloperFullCoverage(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.list_repositories.return_value = ["repo1"]
        self.mock_allowlist.is_allowed.return_value = True

        self.agent = SeniorDeveloperAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist
        )

    @patch('time.sleep')
    def test_process_repositories_sleep(self, mock_sleep):
        # We need to trigger the time.sleep(1) at line 68
        self.agent._analyze_and_task = MagicMock()
        self.agent._process_repositories(["repo1", "repo2"])
        mock_sleep.assert_called_with(1)

    def test_is_same_day_exception(self):
        # Trigger exception at line 142
        self.assertFalse(self.agent._is_same_day({'createTime': 'invalid-date'}, None))

    def test_task_creator_proxies(self):
        # Lines 171, 174, 177, 180, 183
        self.agent.task_creator.create_cicd_task = MagicMock(return_value="cicd")
        self.agent.task_creator.create_feature_implementation_task = MagicMock(return_value="feat")
        self.agent.task_creator.create_tech_debt_task = MagicMock(return_value="debt")
        self.agent.task_creator.create_modernization_task = MagicMock(return_value="mod")
        self.agent.task_creator.create_performance_task = MagicMock(return_value="perf")

        self.assertEqual(self.agent.create_cicd_task("repo", {}), "cicd")
        self.assertEqual(self.agent.create_feature_implementation_task("repo", {}), "feat")
        self.assertEqual(self.agent.create_tech_debt_task("repo", {}), "debt")
        self.assertEqual(self.agent.create_modernization_task("repo", {}), "mod")
        self.assertEqual(self.agent.create_performance_task("repo", {}), "perf")

    def test_analyzer_cicd_missing_workflows_line52(self):
        # We want to cover line 52: `if not workflows: improvements.append("No GitHub Actions workflows found")`
        mock_repo = MagicMock()
        mock_repo.get_contents.side_effect = lambda path: [] if path == ".github/workflows" else ["test"]
        self.mock_github.get_repo.return_value = mock_repo

        res = self.agent.analyzer.analyze_cicd("repo")
        self.assertIn("No GitHub Actions workflows found", res["improvements"])

    def test_analyzer_cicd_missing_tests_line60(self):
        # We want to cover line 60: `if not has_tests: improvements.append("No test directory found - add comprehensive tests")`
        mock_repo = MagicMock()

        def side_effect(path):
            if path == ".github/workflows":
                return [MagicMock(name="workflow.yml")]
            if path == "":
                return [MagicMock(name="src"), MagicMock(name="README.md")] # no test
            return []

        mock_repo.get_contents.side_effect = side_effect
        self.mock_github.get_repo.return_value = mock_repo

        res = self.agent.analyzer.analyze_cicd("repo")
        self.assertIn("No test directory found - add comprehensive tests", res["improvements"])

    def test_analyzer_roadmap_features_no_roadmap(self):
        # Line 86
        mock_repo = MagicMock()
        mock_repo.get_contents.side_effect = UnknownObjectException(404, "Not found")
        self.mock_github.get_repo.return_value = mock_repo

        res = self.agent.analyzer.analyze_roadmap_features("repo")
        self.assertFalse(res["has_features"])

    def test_analyzer_tech_debt_exception_line100(self):
        # We want to cover line 100 which is inside except (UnknownObjectException, GithubException): pass block for tech debt
        # Actually line 100 in the current analyzer is: `if not repo_info.default_branch: return {"needs_attention": False}` inside tech_debt
        mock_repo = MagicMock()
        mock_repo.default_branch = None
        self.mock_github.get_repo.return_value = mock_repo

        res = self.agent.analyzer.analyze_tech_debt("repo")
        self.assertFalse(res["needs_attention"])

    def test_analyzer_tech_debt_exception_line110(self):
        # We want to cover line 110: UnknownObjectException pass
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.side_effect = UnknownObjectException(404, "Not found")
        self.mock_github.get_repo.return_value = mock_repo

        res = self.agent.analyzer.analyze_tech_debt("repo")
        self.assertFalse(res["needs_attention"])

    def test_analyzer_modernization_exception_line125(self):
        # We want to cover line 125: `if not repo_info.default_branch: return {"needs_modernization": False}` inside modernization
        mock_repo = MagicMock()
        mock_repo.default_branch = None
        self.mock_github.get_repo.return_value = mock_repo

        res = self.agent.analyzer.analyze_modernization("repo")
        self.assertFalse(res["needs_modernization"])

    def test_analyzer_performance_exception_line142(self):
        # We want to cover line 142 inside analyze_performance:
        # Actually it's inside `except (UnknownObjectException, GithubException): pass` for `pkg = repo_info.get_contents("package.json")`
        mock_repo = MagicMock()
        mock_tree = MagicMock()
        mock_tree.tree = [MagicMock(path="somefile")]
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.return_value = mock_tree

        def side_effect(path, ref=None):
            if path == "package.json":
                raise UnknownObjectException(404, "Not found")
            return None

        mock_repo.get_contents.side_effect = side_effect
        self.mock_github.get_repo.return_value = mock_repo

        res = self.agent.analyzer.analyze_performance("repo")
        self.assertFalse(res["needs_optimization"])

    def test_analyzer_performance_exception_line168(self):
        # We want to cover the other UnknownObjectException pass block
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.side_effect = UnknownObjectException(404, "Not found")

        # Make package.json pass
        mock_pkg = MagicMock()
        mock_pkg.decoded_content.decode.return_value = '{"dependencies": {"lodash": "1.0"}}'
        def side_effect(path, ref=None):
            if path == "package.json":
                return mock_pkg
            return None

        mock_repo.get_contents.side_effect = side_effect
        self.mock_github.get_repo.return_value = mock_repo

        res = self.agent.analyzer.analyze_performance("repo")
        self.assertTrue(res["needs_optimization"])
        self.assertIn("lodash", res["details"])

    def test_analyzer_modernization_exception_line142(self):
        # We want to cover line 142 inside analyze_modernization
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.side_effect = UnknownObjectException(404, "Not found")
        self.mock_github.get_repo.return_value = mock_repo

        res = self.agent.analyzer.analyze_modernization("repo")
        self.assertFalse(res["needs_modernization"])

if __name__ == '__main__':
    unittest.main()
