
import unittest
from unittest.mock import MagicMock, patch

from src.agents.senior_developer.agent import SeniorDeveloperAgent
from src.agents.senior_developer.analyzers import SeniorDeveloperAnalyzer
from src.agents.senior_developer.utils import extract_session_datetime


class TestSeniorDeveloperEdgeCasesCoverage(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock()
        self.github_client = MagicMock()
        self.allowlist = MagicMock()
        self.telegram = MagicMock()
        with patch("src.agents.senior_developer.agent.get_ai_client", return_value=MagicMock()):
            self.agent = SeniorDeveloperAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")
        self.agent.ai_client = MagicMock()

    def test_analyze_and_task_exceptions(self):
        self.agent.analyzer.analyze_security = MagicMock(return_value={"needs_attention": True})
        self.agent.has_recent_jules_session = MagicMock(return_value=False)
        self.agent.task_creator.create_security_task = MagicMock(return_value={"id": "sec1"})

        self.agent.analyzer.analyze_cicd = MagicMock(return_value={"needs_improvement": True})
        self.agent.task_creator.create_cicd_task = MagicMock(return_value={"id": "ci1"})

        self.agent.analyzer.analyze_roadmap_features = MagicMock(return_value={"has_features": True})
        self.agent.task_creator.create_feature_implementation_task = MagicMock(return_value={"id": "feat1"})

        self.agent.analyzer.analyze_tech_debt = MagicMock(return_value={"needs_attention": True})
        self.agent.task_creator.create_tech_debt_task = MagicMock(return_value={"id": "debt1"})

        self.agent.analyzer.analyze_modernization = MagicMock(return_value={"needs_modernization": True})
        self.agent.task_creator.create_modernization_task = MagicMock(return_value={"id": "mod1"})

        self.agent.analyzer.analyze_performance = MagicMock(return_value={"needs_optimization": True})
        self.agent.task_creator.create_performance_task = MagicMock(return_value={"id": "perf1"})

        results = {"security_tasks": [], "cicd_tasks": [], "feature_tasks": [], "tech_debt_tasks": [], "modernization_tasks": [], "performance_tasks": []}
        self.agent._analyze_and_task("repo", results)

        self.assertEqual(len(results["security_tasks"]), 1)
        self.assertEqual(len(results["cicd_tasks"]), 1)
        self.assertEqual(len(results["feature_tasks"]), 1)
        self.assertEqual(len(results["tech_debt_tasks"]), 1)
        self.assertEqual(len(results["modernization_tasks"]), 1)
        self.assertEqual(len(results["performance_tasks"]), 1)

    def test_analyze_and_task_proxies(self):
        self.agent.task_creator.create_security_task = MagicMock(return_value="sec")
        self.assertEqual(self.agent.task_creator.create_security_task("repo", {}), "sec")

        self.agent.task_creator.create_cicd_task = MagicMock(return_value="ci")
        self.assertEqual(self.agent.task_creator.create_cicd_task("repo", {}), "ci")

        self.agent.task_creator.create_feature_implementation_task = MagicMock(return_value="feat")
        self.assertEqual(self.agent.task_creator.create_feature_implementation_task("repo", {}), "feat")

        self.agent.task_creator.create_tech_debt_task = MagicMock(return_value="debt")
        self.assertEqual(self.agent.task_creator.create_tech_debt_task("repo", {}), "debt")

        self.agent.task_creator.create_modernization_task = MagicMock(return_value="mod")
        self.assertEqual(self.agent.task_creator.create_modernization_task("repo", {}), "mod")

        self.agent.task_creator.create_performance_task = MagicMock(return_value="perf")
        self.assertEqual(self.agent.task_creator.create_performance_task("repo", {}), "perf")

    @patch("src.agents.senior_developer.agent.time.sleep")
    def test_process_repositories_multiple(self, mock_sleep):
        self.agent._analyze_and_task = MagicMock()
        results = self.agent._process_repositories(["repo1", "repo2"])
        mock_sleep.assert_called_once_with(1)

    def test_extract_session_datetime_invalid(self):
        session = {"createTime": "invalid-date"}
        self.assertIsNone(extract_session_datetime(session))
        session = {"createTime": {}}
        self.assertIsNone(extract_session_datetime(session))

    def test_run_end_of_day_session_burst_conditions(self):
        with patch.dict("os.environ", {"JULES_BURST_MAX_ACTIONS": "0"}):
            self.assertEqual(self.agent.burst_mgr.run_burst(["repo"]), [])
        with patch.dict("os.environ", {"JULES_BURST_MAX_ACTIONS": "1", "JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3": "24"}):
            self.assertEqual(self.agent.burst_mgr.run_burst(["repo"]), [])
        with patch.dict("os.environ", {"JULES_BURST_MAX_ACTIONS": "1"}):
            self.assertEqual(self.agent.burst_mgr.run_burst([]), [])
        with patch.dict("os.environ", {"JULES_BURST_MAX_ACTIONS": "1", "JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3": "0", "JULES_DAILY_SESSION_LIMIT": "0"}):
            self.agent.burst_mgr._count_today_sessions = MagicMock(return_value=1)
            self.assertEqual(self.agent.burst_mgr.run_burst(["repo"]), [])

    def test_run_end_of_day_session_burst_action(self):
        with patch.dict("os.environ", {"JULES_BURST_MAX_ACTIONS": "1", "JULES_BURST_TRIGGER_HOUR_UTC_MINUS_3": "0", "JULES_DAILY_SESSION_LIMIT": "10"}):
            self.agent.burst_mgr._count_today_sessions = MagicMock(return_value=0)
            self.agent.burst_mgr._create_burst_task = MagicMock(return_value={"id": "burst1"})
            results = self.agent.burst_mgr.run_burst(["repo"])
            self.assertEqual(len(results), 1)

    def test_execute_burst_action_exception(self):
        self.agent.burst_mgr._create_burst_task = MagicMock(side_effect=Exception("API Error"))
        result = self.agent.burst_mgr._execute_burst_action(["repo"], 0)
        self.assertEqual(result["error"], "API Error")

    def test_count_today_sessions_utc_minus_3_exception(self):
        self.jules_client.list_sessions.side_effect = Exception("API Error")
        self.assertEqual(self.agent.burst_mgr._count_today_sessions(), 0)

    @patch("src.agents.senior_developer.burst_manager.datetime")
    def test_count_today_sessions_utc_minus_3_success(self, mock_datetime):
        from datetime import UTC, datetime, timedelta

        # Use a fixed time to prevent flaky tests due to race conditions around midnight.
        fixed_now = datetime(2024, 1, 1, 2, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = fixed_now
        mock_datetime.fromisoformat.side_effect = datetime.fromisoformat

        now_str = fixed_now.isoformat().replace("+00:00", "Z")
        self.jules_client.list_sessions.return_value = [{"createTime": now_str}]
        self.assertEqual(self.agent.burst_mgr._count_today_sessions(), 1)

    def test_is_same_day_invalid(self):
        from datetime import datetime
        self.assertFalse(self.agent.burst_mgr._is_same_day({}, datetime.now().date()))
        self.assertFalse(self.agent.burst_mgr._is_same_day({"createTime": "invalid"}, datetime.now().date()))

    def test_create_burst_task_no_findings(self):
        self.agent.analyzer.analyze_security = MagicMock(return_value={"needs_attention": False})
        self.agent.analyzer.analyze_security.__name__ = "analyze_security"
        result = self.agent.burst_mgr._create_burst_task("repo", 0)
        self.assertTrue(result["skipped"])

    def test_create_burst_task_success(self):
        self.agent.analyzer.analyze_security = MagicMock(return_value={"needs_attention": True})
        self.agent.analyzer.analyze_security.__name__ = "analyze_security"
        self.agent.task_creator.create_security_task = MagicMock(return_value={"id": "sec1"})
        self.agent.task_creator.create_security_task.__name__ = "create_security_task"
        result = self.agent.burst_mgr._create_burst_task("repo", 0)
        self.assertEqual(result["session_id"], "sec1")

    def test_analyzer_analyze_security_issues_none(self):
        from github.GithubException import UnknownObjectException
        mock_repo = MagicMock()
        mock_repo.get_contents.side_effect = UnknownObjectException(404, "Not found")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_security("repo")
        self.assertTrue(result["needs_attention"])

    def test_analyzer_analyze_security_unexpected_exception(self):
        mock_repo = MagicMock()
        def mock_get_contents(path):
            if path == ".gitignore": return MagicMock(decoded_content=b"")
            raise Exception("API Error")
        mock_repo.get_contents.side_effect = mock_get_contents
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_security("repo")
        self.assertTrue(result["needs_attention"])

    def test_analyzer_analyze_cicd_unexpected_exception(self):
        mock_repo = MagicMock()
        def mock_get_contents(path):
            if path == ".github/workflows": return "exists"
            raise Exception("API Error")
        mock_repo.get_contents.side_effect = mock_get_contents
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_cicd("repo")
        self.assertFalse(result["needs_improvement"])

    def test_analyzer_analyze_roadmap_unexpected_exception(self):
        mock_repo = MagicMock()
        mock_repo.get_contents.side_effect = Exception("API Error")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_roadmap_features("repo")
        self.assertFalse(result["has_features"])

    def test_analyzer_analyze_tech_debt_unexpected_exception(self):
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.side_effect = Exception("API Error")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_tech_debt("repo")
        self.assertFalse(result["needs_attention"])

    def test_analyzer_analyze_modernization_unexpected_exception(self):
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.side_effect = Exception("API Error")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_modernization("repo")
        self.assertFalse(result["needs_modernization"])

    def test_analyzer_analyze_performance_unexpected_exception(self):
        from github.GithubException import UnknownObjectException
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        def mock_get_contents(path):
            raise UnknownObjectException(404, "Not found")
        mock_repo.get_contents.side_effect = mock_get_contents
        mock_repo.get_git_tree.side_effect = Exception("API Error")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_performance("repo")
        self.assertFalse(result["needs_optimization"])

    def test_analyzer_analyze_cicd_unknown_object(self):
        from github.GithubException import UnknownObjectException
        mock_repo = MagicMock()
        def mock_get_contents(path):
            if path == ".github/workflows": return "exists"
            raise UnknownObjectException(404, "Not found")
        mock_repo.get_contents.side_effect = mock_get_contents
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_cicd("repo")
        self.assertTrue(result["needs_improvement"])

    def test_analyzer_analyze_roadmap_unknown_object(self):
        from github.GithubException import UnknownObjectException
        mock_repo = MagicMock()
        mock_repo.get_contents.side_effect = UnknownObjectException(404, "Not found")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_roadmap_features("repo")
        self.assertFalse(result["has_features"])

    def test_analyzer_analyze_tech_debt_unknown_object(self):
        from github.GithubException import UnknownObjectException
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.side_effect = UnknownObjectException(404, "Not found")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_tech_debt("repo")
        self.assertFalse(result["needs_attention"])

    def test_analyzer_analyze_tech_debt_no_branch(self):
        mock_repo = MagicMock()
        mock_repo.default_branch = None
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_tech_debt("repo")
        self.assertFalse(result["needs_attention"])

    def test_analyzer_analyze_modernization_unknown_object(self):
        from github.GithubException import UnknownObjectException
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.side_effect = UnknownObjectException(404, "Not found")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_modernization("repo")
        self.assertFalse(result["needs_modernization"])

    def test_analyzer_analyze_modernization_no_branch(self):
        mock_repo = MagicMock()
        mock_repo.default_branch = None
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_modernization("repo")
        self.assertFalse(result["needs_modernization"])

    def test_analyzer_analyze_performance_unknown_object(self):
        from github.GithubException import UnknownObjectException
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.get_contents.side_effect = UnknownObjectException(404, "Not found")
        mock_repo.get_git_tree.side_effect = UnknownObjectException(404, "Not found")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_performance("repo")
        self.assertFalse(result["needs_optimization"])

    def test_analyzer_analyze_modernization_has_js_ts(self):
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_tree = MagicMock()
        item1 = MagicMock(); item1.path = "app.ts"
        item2 = MagicMock(); item2.path = "legacy.js"
        mock_tree.tree = [item1, item2]
        mock_repo.get_git_tree.return_value = mock_tree
        mock_content = MagicMock()
        mock_content.decoded_content = b"console.log('hello');"
        mock_repo.get_contents.return_value = mock_content
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_modernization("repo")
        self.assertTrue(result["needs_modernization"])
        self.assertIn("Mixed JS/TS codebase - complete TypeScript migration", result["details"])

    def test_analyzer_analyze_modernization_common_js_promise(self):
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_tree = MagicMock()
        item1 = MagicMock(); item1.path = "app.js"
        mock_tree.tree = [item1]
        mock_repo.get_git_tree.return_value = mock_tree
        mock_content = MagicMock()
        mock_content.decoded_content = b"require('fs');\nfetch().then(console.log);"
        mock_repo.get_contents.return_value = mock_content
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_modernization("repo")
        self.assertTrue(result["needs_modernization"])
        self.assertIn("CommonJS detected - migrate to ES Modules", result["details"])
        self.assertIn("Legacy Promise chains detected - refactor to async/await", result["details"])

    def test_analyzer_analyze_performance_unknown_object_pkg(self):
        from github.GithubException import UnknownObjectException
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        def mock_get_contents(path):
            if path == "package.json": raise UnknownObjectException(404, "Not found")
            return MagicMock()
        mock_repo.get_contents.side_effect = mock_get_contents
        mock_tree = MagicMock()
        mock_tree.tree = []
        mock_repo.get_git_tree.return_value = mock_tree
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_performance("repo")
        self.assertFalse(result["needs_optimization"])

    def test_analyzer_analyze_cicd_github_exception(self):
        from github.GithubException import GithubException
        mock_repo = MagicMock()
        def mock_get_contents(path):
            if path == ".github/workflows": return "exists"
            raise GithubException(500, "Error")
        mock_repo.get_contents.side_effect = mock_get_contents
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_cicd("repo")
        self.assertTrue(result["needs_improvement"])

    def test_analyzer_analyze_tech_debt_github_exception(self):
        from github.GithubException import GithubException
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.side_effect = GithubException(500, "Error")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_tech_debt("repo")
        self.assertFalse(result["needs_attention"])

    def test_analyzer_analyze_performance_github_exception(self):
        from github.GithubException import GithubException
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        def mock_get_contents(path):
            if path == "package.json": raise GithubException(500, "Error")
            return MagicMock()
        mock_repo.get_contents.side_effect = mock_get_contents
        mock_repo.get_git_tree.return_value = MagicMock(tree=[])
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_performance("repo")
        self.assertFalse(result["needs_optimization"])

    def test_analyzer_analyze_roadmap_github_exception(self):
        from github.GithubException import GithubException
        mock_repo = MagicMock()
        mock_repo.get_contents.side_effect = GithubException(500, "Error")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_roadmap_features("repo")
        self.assertFalse(result["has_features"])

    def test_analyzer_analyze_modernization_github_exception(self):
        from github.GithubException import GithubException
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.get_git_tree.side_effect = GithubException(500, "Error")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_modernization("repo")
        self.assertFalse(result["needs_modernization"])

    def test_analyzer_analyze_performance_tree_github_exception(self):
        from github.GithubException import GithubException
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        def mock_get_contents(path):
            if path == "package.json": return MagicMock()
        mock_repo.get_contents.side_effect = mock_get_contents
        mock_repo.get_git_tree.side_effect = GithubException(500, "Error")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_performance("repo")
        self.assertFalse(result["needs_optimization"])

    def test_analyzer_analyze_security_dependabot_github_exception(self):
        from github.GithubException import GithubException
        mock_repo = MagicMock()
        def mock_get_contents(path):
            if path == ".gitignore": return MagicMock(decoded_content=b"secrets")
            if path == ".github/dependabot.yml": raise GithubException(500, "Error")
            if path == "renovate.json": raise GithubException(500, "Error")
            return MagicMock()
        mock_repo.get_contents.side_effect = mock_get_contents
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_security("repo")
        self.assertTrue(result["needs_attention"])
        self.assertIn("No automated dependency updates (Dependabot/Renovate)", result["issues"])

    def test_analyzer_analyze_cicd_github_exception_tests(self):
        from github.GithubException import GithubException
        mock_repo = MagicMock()
        def mock_get_contents(path):
            if path == ".github/workflows": return "exists"
            if path == "": raise GithubException(500, "Error")
            return MagicMock()
        mock_repo.get_contents.side_effect = mock_get_contents
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_cicd("repo")
        self.assertTrue(result["needs_improvement"])
        self.assertIn("Empty repository or no files found - add project structure and tests", result["improvements"])

    def test_analyzer_analyze_tech_debt_no_files(self):
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_tree = MagicMock()
        mock_tree.tree = []
        mock_repo.get_git_tree.return_value = mock_tree
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_tech_debt("repo")
        self.assertFalse(result["needs_attention"])

    def test_analyzer_analyze_tech_debt_high_utils(self):
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_tree = MagicMock()
        items = []
        for i in range(6):
            item = MagicMock()
            item.path = f"utils_{i}.py"
            item.size = 100
            items.append(item)
        mock_tree.tree = items
        mock_repo.get_git_tree.return_value = mock_tree
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_tech_debt("repo")
        self.assertTrue(result["needs_attention"])

    def test_analyzer_analyze_modernization_ts_only(self):
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_tree = MagicMock()
        item = MagicMock()
        item.path = "app.ts"
        mock_tree.tree = [item]
        mock_repo.get_git_tree.return_value = mock_tree
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_modernization("repo")
        self.assertFalse(result["needs_modernization"])

    def test_analyzer_analyze_modernization_js_only(self):
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_tree = MagicMock()
        item = MagicMock()
        item.path = "app.js"
        mock_tree.tree = [item]
        mock_repo.get_git_tree.return_value = mock_tree
        mock_content = MagicMock()
        mock_content.decoded_content = b"const x = 1;"
        mock_repo.get_contents.return_value = mock_content
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_modernization("repo")
        self.assertTrue(result["needs_modernization"])
        self.assertIn("Legacy JavaScript codebase - consider TypeScript migration", result["details"])

    def test_analyzer_analyze_performance_large_codebase(self):
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        def mock_get_contents(path):
            if path == "package.json": return MagicMock(decoded_content=b"{}")
            return MagicMock()
        mock_repo.get_contents.side_effect = mock_get_contents
        mock_tree = MagicMock()
        mock_tree.tree = [MagicMock()] * 201
        mock_repo.get_git_tree.return_value = mock_tree
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_performance("repo")
        self.assertTrue(result["needs_optimization"])
        self.assertIn("Large codebase - perform general performance audit", result["details"])

    def test_analyzer_analyze_cicd_no_workflows(self):
        mock_repo = MagicMock()
        def mock_get_contents(path):
            if path == ".github/workflows": return []
            return [MagicMock(name="test")]
        mock_repo.get_contents.side_effect = mock_get_contents
        self.agent.get_repository_info = MagicMock(return_value=mock_repo)
        result = self.agent.analyzer.analyze_cicd("repo")
        self.assertTrue(result["needs_improvement"])
        self.assertIn("No GitHub Actions workflows found", result["improvements"])

    def test_analyzer_proxies(self):
        self.agent.analyzer.analyze_security = MagicMock(return_value="sec")
        self.assertEqual(self.agent.analyzer.analyze_security("repo"), "sec")
        self.agent.analyzer.analyze_cicd = MagicMock(return_value="ci")
        self.assertEqual(self.agent.analyzer.analyze_cicd("repo"), "ci")
        self.agent.analyzer.analyze_roadmap_features = MagicMock(return_value="feat")
        self.assertEqual(self.agent.analyzer.analyze_roadmap_features("repo"), "feat")
        self.agent.analyzer.analyze_tech_debt = MagicMock(return_value="debt")
        self.assertEqual(self.agent.analyzer.analyze_tech_debt("repo"), "debt")
        self.agent.analyzer.analyze_modernization = MagicMock(return_value="mod")
        self.assertEqual(self.agent.analyzer.analyze_modernization("repo"), "mod")
        self.agent.analyzer.analyze_performance = MagicMock(return_value="perf")
        self.assertEqual(self.agent.analyzer.analyze_performance("repo"), "perf")

    def test_persona(self):
        with patch.object(self.agent, "get_instructions_section", return_value="Test Persona"):
            self.assertEqual(self.agent.persona, "Test Persona")

    def test_mission(self):
        with patch.object(self.agent, "get_instructions_section", return_value="Test Mission"):
            self.assertEqual(self.agent.mission, "Test Mission")
