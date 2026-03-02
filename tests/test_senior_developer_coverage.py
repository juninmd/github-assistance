import unittest
from unittest.mock import MagicMock, patch

from src.agents.senior_developer.agent import SeniorDeveloperAgent


class TestSeniorDeveloperCoverage(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.list_repositories.return_value = ["repo1"]
        self.agent = SeniorDeveloperAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_security(self, mock_get_repo):
        repo = MagicMock()
        mock_get_repo.return_value = repo

        # Missing .gitignore
        repo.get_contents.side_effect = Exception("Not found")

        result = self.agent.analyze_security("repo")
        self.assertTrue(result["needs_attention"])
        self.assertIn("Missing .gitignore file", result["issues"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_security_clean(self, mock_get_repo):
        repo = MagicMock()
        mock_get_repo.return_value = repo

        # .gitignore present with .env
        gitignore = MagicMock()
        gitignore.decoded_content.decode.return_value = ".env\nsecrets"

        dependabot = MagicMock()

        def get_contents_side_effect(path):
            if path == ".gitignore":
                return gitignore
            if path == ".github/dependabot.yml":
                return dependabot
            raise Exception("Not found")

        repo.get_contents.side_effect = get_contents_side_effect

        result = self.agent.analyze_security("repo")
        self.assertFalse(result["needs_attention"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_cicd(self, mock_get_repo):
        repo = MagicMock()
        mock_get_repo.return_value = repo

        # No workflows, no tests
        repo.get_contents.side_effect = Exception("Not found")

        result = self.agent.analyze_cicd("repo")
        self.assertTrue(result["needs_improvement"])
        self.assertIn("Set up GitHub Actions for CI/CD", result["improvements"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_cicd_clean(self, mock_get_repo):
        repo = MagicMock()
        mock_get_repo.return_value = repo

        item_test = MagicMock()
        item_test.name = "tests"

        def get_contents_side_effect(path):
            if path == ".github/workflows":
                return [MagicMock()]
            if path == "":
                return [item_test]
            raise Exception("Not found")

        repo.get_contents.side_effect = get_contents_side_effect

        result = self.agent.analyze_cicd("repo")
        self.assertFalse(result["needs_improvement"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_roadmap_features(self, mock_get_repo):
        repo = MagicMock()
        mock_get_repo.return_value = repo

        # ROADMAP.md exists
        repo.get_contents.return_value = MagicMock()

        # Feature issues exist
        issue = MagicMock()
        issue.title = "Feature 1"
        issue.number = 1
        label = MagicMock()
        label.name = "feature"
        issue.labels = [label]

        repo.get_issues.return_value = [issue]

        result = self.agent.analyze_roadmap_features("repo")
        self.assertTrue(result["has_features"])
        self.assertEqual(len(result["features"]), 1)

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_roadmap_features_none(self, mock_get_repo):
        repo = MagicMock()
        mock_get_repo.return_value = repo

        repo.get_contents.side_effect = Exception("Not found")

        result = self.agent.analyze_roadmap_features("repo")
        self.assertFalse(result["has_features"])

    def test_run_empty_allowlist(self):
        self.mock_allowlist.list_repositories.return_value = []
        result = self.agent.run()
        self.assertEqual(result["status"], "skipped")

    def test_run_exception(self):
        self.mock_allowlist.list_repositories.return_value = ["repo1"]
        with patch.object(self.agent.analyzer, 'analyze_security', side_effect=Exception("Error")):
             result = self.agent.run()
             self.assertEqual(len(result["failed"]), 1)

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_methods_repo_none(self, mock_get_repo):
        mock_get_repo.return_value = None
        self.assertFalse(self.agent.analyze_security("repo")["needs_attention"])
        self.assertFalse(self.agent.analyze_cicd("repo")["needs_improvement"])
        self.assertFalse(self.agent.analyze_roadmap_features("repo")["has_features"])
        self.assertFalse(self.agent.analyze_tech_debt("repo")["needs_attention"])
        self.assertFalse(self.agent.analyze_modernization("repo")["needs_modernization"])
        self.assertFalse(self.agent.analyze_performance("repo")["needs_optimization"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_tech_debt_exception(self, mock_get_repo):
        repo = MagicMock()
        mock_get_repo.return_value = repo
        repo.get_git_tree.side_effect = Exception("Error")

        result = self.agent.analyze_tech_debt("repo")
        self.assertFalse(result["needs_attention"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_modernization_exception(self, mock_get_repo):
        repo = MagicMock()
        mock_get_repo.return_value = repo
        repo.get_git_tree.side_effect = Exception("Error")

        result = self.agent.analyze_modernization("repo")
        self.assertFalse(result["needs_modernization"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_performance_exception(self, mock_get_repo):
        repo = MagicMock()
        mock_get_repo.return_value = repo
        repo.get_contents.side_effect = Exception("Error")
        repo.get_git_tree.side_effect = Exception("Error")

        result = self.agent.analyze_performance("repo")
        self.assertFalse(result["needs_optimization"])
