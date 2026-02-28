import unittest
from unittest.mock import MagicMock, patch
from src.agents.senior_developer.agent import SeniorDeveloperAgent

class TestSeniorDeveloperAgent(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.list_repositories.return_value = ["juninmd/test-repo"]

        patcher = patch('src.agents.senior_developer.agent.get_ai_client')
        self.mock_get_ai_client = patcher.start()
        self.addCleanup(patcher.stop)

        self.agent = SeniorDeveloperAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

    def test_init_with_ai_parameters(self):
        SeniorDeveloperAgent(
            self.mock_jules, self.mock_github, self.mock_allowlist,
            ai_provider="ollama", ai_model="llama3", ai_config={"base_url": "http://test"}
        )
        self.mock_get_ai_client.assert_called_with("ollama", base_url="http://test", model="llama3")

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_modernization_js_to_ts(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_tree = MagicMock()
        mock_tree.tree = [MagicMock(path="src/index.js"), MagicMock(path="src/types.ts")]
        mock_repo.default_branch = "master"
        mock_repo.get_git_tree.return_value = mock_tree
        mock_content = MagicMock()
        mock_content.decoded_content.decode.return_value = "require('express');"
        mock_repo.get_contents.return_value = mock_content

        result = self.agent.analyzer.analyze_modernization("repo")
        self.assertTrue(result["needs_modernization"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_tech_debt_large_files(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_tree = MagicMock()
        mock_tree.tree = [MagicMock(path="src/big.py", size=30000)]
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.return_value = mock_tree

        result = self.agent.analyzer.analyze_tech_debt("repo")
        self.assertTrue(result["needs_attention"])

    @patch.object(SeniorDeveloperAgent, 'get_repository_info')
    def test_analyze_performance_heavy_deps(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_pkg = MagicMock()
        mock_pkg.decoded_content.decode.return_value = '{"dependencies": {"lodash": "1.0"}}'
        mock_repo.get_contents.return_value = mock_pkg

        result = self.agent.analyzer.analyze_performance("repo")
        self.assertTrue(result["needs_optimization"])

    @patch.object(SeniorDeveloperAgent, 'create_jules_session')
    def test_run_executes_all_analyses(self, mock_create_session):
        self.agent.analyzer.analyze_security = MagicMock(return_value={"needs_attention": True})
        self.agent.analyzer.analyze_cicd = MagicMock(return_value={"needs_improvement": True})
        self.agent.analyzer.analyze_roadmap_features = MagicMock(return_value={"has_features": True, "features": []})
        self.agent.analyzer.analyze_tech_debt = MagicMock(return_value={"needs_attention": True})
        self.agent.analyzer.analyze_modernization = MagicMock(return_value={"needs_modernization": True})
        self.agent.analyzer.analyze_performance = MagicMock(return_value={"needs_optimization": True})
        
        mock_create_session.return_value = {"id": "sid"}
        with patch.object(self.agent, 'load_jules_instructions', return_value="inst"):
            results = self.agent.run()

        for key in ["security_tasks", "cicd_tasks", "feature_tasks", "tech_debt_tasks", "modernization_tasks", "performance_tasks"]:
            self.assertEqual(len(results[key]), 1)

    @patch.object(SeniorDeveloperAgent, 'create_jules_session')
    def test_create_security_task(self, mock_create_session):
        mock_create_session.return_value = {"id": "sec-1"}
        with patch.object(self.agent, 'load_jules_instructions', return_value="Fix"):
            result = self.agent.task_creator.create_security_task("repo", {"issues": ["i"]})
            self.assertEqual(result["id"], "sec-1")

    @patch.object(SeniorDeveloperAgent, 'create_burst_task')
    @patch.object(SeniorDeveloperAgent, 'count_today_sessions_utc_minus_3')
    @patch('src.agents.senior_developer.agent.getenv')
    def test_run_end_of_day_session_burst_respects_limits(self, mock_getenv, mock_count, mock_create_burst):
        mock_getenv.side_effect = lambda k, d=None: {'JULES_BURST_MAX_ACTIONS': '2', 'JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3': '0', 'JULES_DAILY_SESSION_LIMIT': '100'}.get(k, d)
        mock_count.return_value = 98
        mock_create_burst.return_value = {'sid': 's'}
        results = self.agent.run_end_of_day_session_burst(['repo'])
        self.assertEqual(len(results), 2)

    def test_is_same_day(self):
        from datetime import date
        target = date(2026, 1, 1)
        self.assertTrue(self.agent._is_same_day({'createTime': '2026-01-01T03:00:00Z'}, target))
        self.assertFalse(self.agent._is_same_day({'createTime': '2026-01-02T03:00:00Z'}, target))

if __name__ == '__main__':
    unittest.main()
