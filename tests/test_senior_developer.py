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
        mock_repo.default_branch = "master"
        mock_repo.get_git_tree.return_value = mock_tree

        # Simulate CommonJS content
        mock_content = MagicMock()
        mock_content.decoded_content.decode.return_value = "const express = require('express'); module.exports = express;"
        mock_repo.get_contents.return_value = mock_content

        result = self.agent.analyze_modernization("juninmd/test-repo")
        
        self.assertTrue(result["needs_modernization"])
        self.assertIn("complete TypeScript migration", result["details"])
        self.assertIn("CommonJS detected", result["details"])
        mock_repo.get_git_tree.assert_called_once_with("master", recursive=True)

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_tech_debt_large_files(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        
        mock_tree = MagicMock()
        item1 = MagicMock(path="src/complex_logic.py", size=30000) # > 20KB
        item2 = MagicMock(path="src/utils/math.py", size=1000)
        mock_tree.tree = [item1, item2]
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.return_value = mock_tree

        result = self.agent.analyze_tech_debt("juninmd/test-repo")
        
        self.assertTrue(result["needs_attention"])
        self.assertIn("Large file detected", result["details"])
        self.assertIn("complex_logic.py", result["details"])
        mock_repo.get_git_tree.assert_called_once_with("main", recursive=True)

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

    @patch.object(SeniorDeveloperAgent, 'create_jules_session')
    def test_run_executes_all_analyses(self, mock_create_session):
        # Mock all internal analyses to return 'needs action'
        self.agent.analyze_security = MagicMock(return_value={"needs_attention": True, "issues": ["Mock Issue"]})
        self.agent.analyze_cicd = MagicMock(return_value={"needs_improvement": True, "improvements": ["Mock Imp"]})
        self.agent.analyze_roadmap_features = MagicMock(return_value={"has_features": True, "features": [{"title": "F1", "number": 1}]})
        self.agent.analyze_tech_debt = MagicMock(return_value={"needs_attention": True, "details": "Debt details"})
        self.agent.analyze_modernization = MagicMock(return_value={"needs_modernization": True, "details": "Mod details"})
        self.agent.analyze_performance = MagicMock(return_value={"needs_optimization": True, "details": "Perf details"})
        
        mock_create_session.return_value = {"id": "mock_session_id"}
        
        # Patch load_jules_instructions to avoid file I/O errors in test
        with patch.object(self.agent, 'load_jules_instructions', return_value="mock instructions"):
            results = self.agent.run()

        self.assertEqual(len(results["security_tasks"]), 1)
        self.assertEqual(len(results["cicd_tasks"]), 1)
        self.assertEqual(len(results["feature_tasks"]), 1)
        self.assertEqual(len(results["tech_debt_tasks"]), 1)
        self.assertEqual(len(results["modernization_tasks"]), 1)
        self.assertEqual(len(results["performance_tasks"]), 1)

    @patch.object(SeniorDeveloperAgent, 'create_jules_session')
    def test_create_security_task(self, mock_create_session):
        mock_create_session.return_value = {"id": "sec-1"}
        analysis = {"issues": ["Weak password", "Open port"]}

        with patch.object(self.agent, 'load_jules_instructions', return_value="Fix security"):
            result = self.agent.create_security_task("juninmd/test-repo", analysis)

            self.assertEqual(result["id"], "sec-1")
            mock_create_session.assert_called_once()
            _, kwargs = mock_create_session.call_args
            self.assertEqual(kwargs['title'], "Security Hardening for juninmd/test-repo")

    @patch.object(SeniorDeveloperAgent, 'create_jules_session')
    def test_create_cicd_task(self, mock_create_session):
        mock_create_session.return_value = {"id": "cicd-1"}
        analysis = {"improvements": ["Add linting", "Add testing"]}

        with patch.object(self.agent, 'load_jules_instructions', return_value="Setup CI"):
            result = self.agent.create_cicd_task("juninmd/test-repo", analysis)

            self.assertEqual(result["id"], "cicd-1")
            mock_create_session.assert_called_once()
            _, kwargs = mock_create_session.call_args
            self.assertEqual(kwargs['title'], "CI/CD Pipeline for juninmd/test-repo")

    @patch.object(SeniorDeveloperAgent, 'create_jules_session')
    def test_create_feature_implementation_task(self, mock_create_session):
        mock_create_session.return_value = {"id": "feat-1"}
        analysis = {"features": [{"title": "Login", "number": 10}]}

        with patch.object(self.agent, 'load_jules_instructions', return_value="Build feature"):
            result = self.agent.create_feature_implementation_task("juninmd/test-repo", analysis)

            self.assertEqual(result["id"], "feat-1")
            mock_create_session.assert_called_once()
            _, kwargs = mock_create_session.call_args
            self.assertEqual(kwargs['title'], "Feature Implementation for juninmd/test-repo")

    @patch.object(SeniorDeveloperAgent, 'create_jules_session')
    def test_create_tech_debt_task(self, mock_create_session):
        mock_create_session.return_value = {"id": "debt-1"}
        analysis = {"details": "Refactor code"}

        with patch.object(self.agent, 'load_jules_instructions', return_value="Reduce debt"):
            result = self.agent.create_tech_debt_task("juninmd/test-repo", analysis)

            self.assertEqual(result["id"], "debt-1")
            mock_create_session.assert_called_once()
            _, kwargs = mock_create_session.call_args
            self.assertEqual(kwargs['title'], "Tech Debt Cleanup for juninmd/test-repo")

    @patch.object(SeniorDeveloperAgent, 'create_jules_session')
    def test_create_modernization_task(self, mock_create_session):
        mock_create_session.return_value = {"id": "mod-1"}
        analysis = {"details": "Migrate to TS"}

        with patch.object(self.agent, 'load_jules_instructions', return_value="Modernize code"):
            result = self.agent.create_modernization_task("juninmd/test-repo", analysis)

            self.assertEqual(result["id"], "mod-1")
            mock_create_session.assert_called_once()
            _, kwargs = mock_create_session.call_args
            self.assertEqual(kwargs['title'], "Modernization for juninmd/test-repo")

    @patch.object(SeniorDeveloperAgent, 'create_jules_session')
    def test_create_performance_task(self, mock_create_session):
        mock_create_session.return_value = {"id": "perf-1"}
        analysis = {"details": "Optimize loops"}

        with patch.object(self.agent, 'load_jules_instructions', return_value="Optimize perf"):
            result = self.agent.create_performance_task("juninmd/test-repo", analysis)

            self.assertEqual(result["id"], "perf-1")
            mock_create_session.assert_called_once()
            _, kwargs = mock_create_session.call_args
            self.assertEqual(kwargs['title'], "Performance Tuning for juninmd/test-repo")


    @patch.object(SeniorDeveloperAgent, 'create_burst_task')
    @patch.object(SeniorDeveloperAgent, 'count_today_sessions_utc_minus_3')
    @patch('src.agents.senior_developer.agent.getenv')
    def test_run_end_of_day_session_burst_respects_limits(self, mock_getenv, mock_count, mock_create_burst):
        mock_getenv.side_effect = lambda key, default=None: {
            'JULES_BURST_MAX_ACTIONS': '4',
            'JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3': '0',
            'JULES_DAILY_SESSION_LIMIT': '100',
        }.get(key, default)
        mock_count.return_value = 98
        mock_create_burst.return_value = {'session_id': 'sid'}

        results = self.agent.run_end_of_day_session_burst(['juninmd/test-repo'])

        self.assertEqual(len(results), 2)
        self.assertEqual(mock_create_burst.call_count, 2)

    def test_extract_session_datetime_from_create_time(self):
        dt = self.agent.extract_session_datetime({'createTime': '2026-01-01T03:00:00Z'})
        self.assertIsNotNone(dt)

if __name__ == '__main__':
    unittest.main()
