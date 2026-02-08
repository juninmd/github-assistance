import unittest
from unittest.mock import MagicMock, patch
from src.agents.senior_developer.agent import SeniorDeveloperAgent

class TestSeniorDeveloperAgent(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.list_repositories.return_value = ["juninmd/test-repo"]
        self.agent = SeniorDeveloperAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_modernization_js_to_ts(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        
        # Simulate a codebase with both JS and TS files
        mock_tree = MagicMock()
        item1 = MagicMock(path="src/index.js")
        item2 = MagicMock(path="src/types.ts")
        mock_tree.tree = [item1, item2]
        mock_repo.get_git_tree.return_value = mock_tree

        # Simulate CommonJS content
        mock_content = MagicMock()
        mock_content.decoded_content.decode.return_value = "const express = require('express'); module.exports = express;"
        mock_repo.get_contents.return_value = mock_content

        result = self.agent.analyze_modernization("juninmd/test-repo")
        
        self.assertTrue(result["needs_modernization"])
        self.assertIn("complete TypeScript migration", result["details"])
        self.assertIn("CommonJS detected", result["details"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_tech_debt_large_files(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        
        mock_tree = MagicMock()
        item1 = MagicMock(path="src/complex_logic.py", size=30000) # > 20KB
        item2 = MagicMock(path="src/utils/math.py", size=1000)
        mock_tree.tree = [item1, item2]
        mock_repo.get_git_tree.return_value = mock_tree

        result = self.agent.analyze_tech_debt("juninmd/test-repo")
        
        self.assertTrue(result["needs_attention"])
        self.assertIn("Large file detected", result["details"])
        self.assertIn("complex_logic.py", result["details"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_performance_heavy_deps(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        
        # Mock package.json with lodash
        mock_pkg = MagicMock()
        mock_pkg.decoded_content.decode.return_value = '{"dependencies": {"lodash": "^4.17.21"}}'
        
        def get_contents_side_effect(path):
            if path == "package.json":
                return mock_pkg
            raise Exception("File not found")
        
        mock_repo.get_contents.side_effect = get_contents_side_effect

        result = self.agent.analyze_performance("juninmd/test-repo")
        
        self.assertTrue(result["needs_optimization"])
        self.assertIn("heavy utility library (lodash)", result["details"])

    @patch.object(SeniorDeveloperAgent, 'create_jules_task')
    def test_run_executes_all_analyses(self, mock_create_task):
        # Mock all internal analyses to return 'needs action'
        self.agent.analyze_security = MagicMock(return_value={"needs_attention": True, "issues": ["Mock Issue"]})
        self.agent.analyze_cicd = MagicMock(return_value={"needs_improvement": True, "improvements": ["Mock Imp"]})
        self.agent.analyze_roadmap_features = MagicMock(return_value={"has_features": True, "features": [{"title": "F1", "number": 1}]})
        self.agent.analyze_tech_debt = MagicMock(return_value={"needs_attention": True, "details": "Debt details"})
        self.agent.analyze_modernization = MagicMock(return_value={"needs_modernization": True, "details": "Mod details"})
        self.agent.analyze_performance = MagicMock(return_value={"needs_optimization": True, "details": "Perf details"})
        
        mock_create_task.return_value = {"task_id": "mock_id"}
        
        # Patch load_jules_instructions to avoid file I/O errors in test
        with patch.object(self.agent, 'load_jules_instructions', return_value="mock instructions"):
            results = self.agent.run()

        self.assertEqual(len(results["security_tasks"]), 1)
        self.assertEqual(len(results["cicd_tasks"]), 1)
        self.assertEqual(len(results["feature_tasks"]), 1)
        self.assertEqual(len(results["tech_debt_tasks"]), 1)
        self.assertEqual(len(results["modernization_tasks"]), 1)
        self.assertEqual(len(results["performance_tasks"]), 1)

if __name__ == '__main__':
    unittest.main()
