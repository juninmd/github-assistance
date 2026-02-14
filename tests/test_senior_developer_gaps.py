import unittest
from unittest.mock import MagicMock, patch
from src.agents.senior_developer.agent import SeniorDeveloperAgent

class TestSeniorDeveloperGaps(unittest.TestCase):
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

    def test_run_exception(self):
        # Force an exception inside the loop by making a task creation fail
        with patch.object(self.agent, 'analyze_security', return_value={"needs_attention": True}):
             with patch.object(self.agent, 'create_security_task', side_effect=Exception("Task Fail")):
                  results = self.agent.run()
                  self.assertEqual(len(results["failed"]), 1)
                  self.assertIn("Task Fail", results["failed"][0]["error"])

    def test_analyze_security_exception(self):
        self.mock_github.get_repo.side_effect = Exception("API Fail")
        result = self.agent.analyze_security("repo")
        self.assertFalse(result["needs_attention"])

    def test_analyze_cicd_exception(self):
        self.mock_github.get_repo.side_effect = Exception("API Fail")
        result = self.agent.analyze_cicd("repo")
        self.assertFalse(result["needs_improvement"])

    def test_analyze_tech_debt_many_utils(self):
        repo_info = MagicMock()
        # Create 6 utils files
        tree_items = []
        for i in range(6):
            item = MagicMock()
            item.path = f"src/utils/util_{i}.py"
            item.size = 100
            tree_items.append(item)

        repo_info.get_git_tree.return_value.tree = tree_items
        self.mock_github.get_repo.return_value = repo_info

        result = self.agent.analyze_tech_debt("repo")
        self.assertTrue(result["needs_attention"])
        self.assertIn("High number of utility files", result["details"])

    def test_analyze_modernization_js_only(self):
        repo_info = MagicMock()
        item_js = MagicMock(); item_js.path = "index.js"
        repo_info.get_git_tree.return_value.tree = [item_js]

        self.mock_github.get_repo.return_value = repo_info

        # Mock content check for require/then to be false to isolate the js_only check
        repo_info.get_contents.return_value.decoded_content = b"console.log('hi')"

        result = self.agent.analyze_modernization("repo")
        self.assertTrue(result["needs_modernization"])
        self.assertIn("Legacy JavaScript codebase", result["details"])

    def test_analyze_modernization_legacy_promises(self):
        repo_info = MagicMock()
        item_js = MagicMock(); item_js.path = "index.js"
        repo_info.get_git_tree.return_value.tree = [item_js]

        self.mock_github.get_repo.return_value = repo_info

        repo_info.get_contents.return_value.decoded_content = b"doSomething().then(res => {})"

        result = self.agent.analyze_modernization("repo")
        self.assertTrue(result["needs_modernization"])
        self.assertIn("Legacy Promise chains", result["details"])

    def test_analyze_performance_large_codebase(self):
        repo_info = MagicMock()
        # Create 201 files
        tree_items = [MagicMock(path=f"file{i}") for i in range(201)]
        repo_info.get_git_tree.return_value.tree = tree_items
        self.mock_github.get_repo.return_value = repo_info

        # Make package.json retrieval fail to ignore that part
        repo_info.get_contents.side_effect = Exception("No package.json")

        result = self.agent.analyze_performance("repo")
        self.assertTrue(result["needs_optimization"])
        self.assertIn("Large codebase", result["details"])

if __name__ == '__main__':
    unittest.main()
