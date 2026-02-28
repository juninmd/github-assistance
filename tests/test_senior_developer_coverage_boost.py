import unittest
from unittest.mock import MagicMock, patch
from datetime import date
from github.GithubException import GithubException
from src.agents.senior_developer.agent import SeniorDeveloperAgent
from src.agents.senior_developer.analyzers import SeniorDeveloperAnalyzer

class TestSeniorDeveloperCoverageBoost(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.agent = SeniorDeveloperAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        self.analyzer = SeniorDeveloperAnalyzer(self.agent)

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_security_branches(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        
        # Test missing .gitignore
        mock_repo.get_contents.side_effect = Exception("Not found")
        result = self.analyzer.analyze_security("repo")
        self.assertIn("Missing .gitignore file", result["issues"])
        
        # Test .env not in .gitignore and missing dependency updates
        mock_repo.get_contents.side_effect = None
        mock_gitignore = MagicMock()
        mock_gitignore.decoded_content.decode.return_value = "node_modules/\n"
        
        def side_effect(path):
            if path == ".gitignore":
                return mock_gitignore
            raise GithubException(404, "Not Found", {})
            
        mock_repo.get_contents.side_effect = side_effect
        result = self.analyzer.analyze_security("repo")
        self.assertIn("Missing .env in .gitignore", result["issues"])
        self.assertIn("No automated dependency updates (Dependabot/Renovate)", result["issues"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_cicd_no_workflows(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        
        # Test no workflows directory
        mock_repo.get_contents.side_effect = GithubException(404, "Not Found", {})
        result = self.analyzer.analyze_cicd("repo")
        self.assertIn("Set up GitHub Actions for CI/CD", result["improvements"])
        self.assertIn("Empty repository or no files found - add project structure and tests", result["improvements"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_roadmap_features_branches(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        
        # Test ROADMAP.md exists and has feature issues
        mock_roadmap = MagicMock()
        mock_repo.get_contents.return_value = mock_roadmap
        
        mock_issue = MagicMock()
        mock_issue.title = "Feature 1"
        mock_issue.number = 1
        mock_label = MagicMock()
        mock_label.name = "feature"
        mock_issue.labels = [mock_label]
        mock_repo.get_issues.return_value = [mock_issue]
        
        result = self.analyzer.analyze_roadmap_features("repo")
        self.assertTrue(result["has_features"])
        self.assertEqual(len(result["features"]), 1)

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_tech_debt_high_utils(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.default_branch = "main"
        
        mock_tree = MagicMock()
        mock_tree.tree = [MagicMock(path=f"utils/file{i}.py", size=100) for i in range(10)]
        mock_repo.get_git_tree.return_value = mock_tree
        
        result = self.analyzer.analyze_tech_debt("repo")
        self.assertTrue(result["needs_attention"])
        self.assertIn("High number of utility files (10)", result["details"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_modernization_legacy_js(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.default_branch = "main"
        
        mock_tree = MagicMock()
        mock_tree.tree = [MagicMock(path="src/old.js")]
        mock_repo.get_git_tree.return_value = mock_tree
        
        mock_content = MagicMock()
        mock_content.decoded_content.decode.return_value = "module.exports = {};"
        mock_repo.get_contents.return_value = mock_content
        
        result = self.analyzer.analyze_modernization("repo")
        self.assertTrue(result["needs_modernization"])
        self.assertIn("Legacy JavaScript codebase", result["details"])
        self.assertIn("CommonJS detected", result["details"])

    def test_agent_proxies(self):
        # Verification of agent proxies added for compatibility
        with patch.object(self.agent.analyzer, 'analyze_security') as m:
            self.agent.analyze_security("repo")
            m.assert_called_once()
        with patch.object(self.agent.task_creator, 'create_security_task') as m:
            self.agent.create_security_task("repo", {})
            m.assert_called_once()

if __name__ == '__main__':
    unittest.main()
