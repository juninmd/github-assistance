import unittest
from unittest.mock import MagicMock, patch

from src.agents.product_manager.agent import ProductManagerAgent


class TestProductManagerAgent(unittest.TestCase):
    def setUp(self):
        self._get_ai_client_patcher = patch("src.agents.product_manager.agent.get_ai_client", return_value=None)
        self._get_ai_client_patcher.start()
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.agent = ProductManagerAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

    def tearDown(self):
        self._get_ai_client_patcher.stop()

    def test_run_empty_allowlist(self):
        self.mock_allowlist.list_repositories.return_value = []
        result = self.agent.run()
        self.assertEqual(result["status"], "skipped")

    def test_run_success(self):
        self.mock_allowlist.list_repositories.return_value = ["repo1"]

        # Mock analyze_and_create_roadmap
        with patch.object(self.agent, 'analyze_and_create_roadmap', return_value="success") as mock_analyze:
            result = self.agent.run()
            self.assertEqual(len(result["processed"]), 1)
            mock_analyze.assert_called_with("repo1")

    def test_run_failure(self):
        self.mock_allowlist.list_repositories.return_value = ["repo1"]

        # Mock analyze_and_create_roadmap to fail
        with patch.object(self.agent, 'analyze_and_create_roadmap', side_effect=Exception("Failed")):
            result = self.agent.run()
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(result["failed"][0]["repository"], "repo1")

    def test_analyze_and_create_roadmap(self):
        repo_info = MagicMock()
        self.mock_github.get_repo.return_value = repo_info

        with patch.object(self.agent, '_is_roadmap_up_to_date', return_value=False):
            with patch.object(self.agent, 'has_recent_jules_session', return_value=False):
                with patch.object(self.agent, 'analyze_repository', return_value={"summary": "ok", "priorities": []}) as mock_analyze_repo:
                    with patch.object(self.agent, 'generate_roadmap_instructions', return_value="instructions") as mock_gen_instr:
                        with patch.object(self.agent, 'create_jules_session', return_value={"id": "123"}) as mock_create_session:
                            result = self.agent.analyze_and_create_roadmap("repo1")

                            self.assertEqual(result["session_id"], "123")
                            mock_analyze_repo.assert_called()
                            mock_gen_instr.assert_called()
                            mock_create_session.assert_called()

    def test_analyze_and_create_roadmap_skipped_up_to_date(self):
        repo_info = MagicMock()
        self.mock_github.get_repo.return_value = repo_info

        with patch.object(self.agent, '_is_roadmap_up_to_date', return_value=True):
            result = self.agent.analyze_and_create_roadmap("repo1")
            self.assertEqual(result["skipped"], True)
            self.assertEqual(result["reason"], "roadmap_up_to_date")

    def test_analyze_and_create_roadmap_skipped_recent_session(self):
        repo_info = MagicMock()
        self.mock_github.get_repo.return_value = repo_info

        with patch.object(self.agent, '_is_roadmap_up_to_date', return_value=False):
            with patch.object(self.agent, 'has_recent_jules_session', return_value=True):
                result = self.agent.analyze_and_create_roadmap("repo1")
                self.assertEqual(result["skipped"], True)
                self.assertEqual(result["reason"], "recent_session_exists")

    def test__is_roadmap_up_to_date(self):
        repo = MagicMock()
        mock_commit = MagicMock()

        from datetime import UTC, datetime, timedelta

        # Test fresh roadmap
        mock_commit.commit.author.date = datetime.now(UTC) - timedelta(days=2)
        repo.get_commits.return_value = [mock_commit]
        self.assertTrue(self.agent._is_roadmap_up_to_date(repo))

        # Test stale roadmap
        mock_commit.commit.author.date = datetime.now(UTC) - timedelta(days=10)
        repo.get_commits.return_value = [mock_commit]
        self.assertFalse(self.agent._is_roadmap_up_to_date(repo))

        # Test no commits
        repo.get_commits.return_value = []
        self.assertFalse(self.agent._is_roadmap_up_to_date(repo))

        # Test GithubException
        from github import GithubException
        repo.get_commits.side_effect = GithubException(status=404, data="Not Found")
        self.assertFalse(self.agent._is_roadmap_up_to_date(repo))

        # Test generic exception
        repo.get_commits.side_effect = Exception("General error")
        self.assertFalse(self.agent._is_roadmap_up_to_date(repo))

    def test_analyze_and_create_roadmap_repo_not_found(self):
        self.mock_github.get_repo.side_effect = Exception("Not found")
        with self.assertRaises(ValueError):
            self.agent.analyze_and_create_roadmap("repo1")

    def test_analyze_repository(self):
        self.agent._ai_client = MagicMock()  # pyright: ignore[reportAttributeAccessIssue]
        repo_info = MagicMock()
        repo_info.description = "Test Description"
        repo_info.language = "Python"

        issue1 = MagicMock()
        issue1.labels = [MagicMock(name="bug")]
        issue1.labels[0].name = "bug"

        issue2 = MagicMock()
        issue2.labels = [MagicMock(name="feature")]
        issue2.labels[0].name = "feature"

        repo_info.get_issues.return_value = [issue1, issue2]

        with patch.object(self.agent, '_analyze_issues_with_ai') as mock_ai:
            mock_ai.return_value = {
                "ai_summary": "AI summary",
                "priorities": [
                    {"category": "AI Bugs", "count": 2, "urgency": "high"}
                ]
            }

            result = self.agent.analyze_repository("repo1", repo_info)

            self.assertEqual(result["total_issues"], 2)
            self.assertEqual(result["summary"], "AI summary")
            # Verify AI priorities are used
            self.assertEqual(result["priorities"][0]["category"], "AI Bugs")
            mock_ai.assert_called_with([issue1, issue2], "Test Description")

    def test_analyze_repository_ai_returns_empty(self):
        self.agent._ai_client = MagicMock()  # pyright: ignore[reportAttributeAccessIssue]
        repo_info = MagicMock()
        repo_info.description = "Test Description"
        repo_info.language = "Python"

        issue1 = MagicMock()
        issue1.labels = [MagicMock(name="bug")]
        issue1.labels[0].name = "bug"

        issue2 = MagicMock()
        issue2.labels = [MagicMock(name="feature")]
        issue2.labels[0].name = "feature"

        repo_info.get_issues.return_value = [issue1, issue2]

        with patch.object(self.agent, '_analyze_issues_with_ai') as mock_ai:
            mock_ai.return_value = {}

            result = self.agent.analyze_repository("repo1", repo_info)

            self.assertEqual(result["total_issues"], 2)
            # Verify fallback logic
            priorities = {p['category']: p['count'] for p in result['priorities']}
            self.assertEqual(priorities["Bugs"], 1)
            self.assertEqual(priorities["Features"], 1)
            self.assertIn("Repository has 2 open issues", result["summary"])

    def test__analyze_issues_with_ai(self):
        issue = MagicMock()
        issue.number = 1
        issue.title = "Test Issue"
        issue.labels = [MagicMock()]
        issue.labels[0].name = "bug"

        expected_json = '{"ai_summary": "Test", "priorities": [{"category": "Bugs", "count": 1, "urgency": "high"}]}'

        mock_client = MagicMock()
        mock_client.generate.return_value = expected_json
        self.agent._ai_client = mock_client  # pyright: ignore[reportAttributeAccessIssue]

        result = self.agent._analyze_issues_with_ai([issue], "Test Repo")
        self.assertEqual(result["ai_summary"], "Test")
        self.assertEqual(len(result["priorities"]), 1)
        mock_client.generate.assert_called_once()

    def test__analyze_issues_with_ai_empty_issues(self):
        result = self.agent._analyze_issues_with_ai([], "Test")
        self.assertEqual(result, {})

    def test__analyze_issues_with_ai_no_client(self):
        self.agent._ai_client = None  # pyright: ignore[reportAttributeAccessIssue]
        result = self.agent._analyze_issues_with_ai([MagicMock()], "Test")
        self.assertEqual(result, {})

    def test__analyze_issues_with_ai_exception(self):
        mock_client = MagicMock()
        mock_client.generate.side_effect = Exception("API error")
        self.agent._ai_client = mock_client  # pyright: ignore[reportAttributeAccessIssue]

        result = self.agent._analyze_issues_with_ai([MagicMock()], "Test")
        self.assertEqual(result, {})

    def test_generate_roadmap_instructions(self):
        analysis = {
            "repository_description": "Desc",
            "main_language": "Python",
            "total_issues": 10,
            "priorities": [{"category": "Bugs", "count": 5, "urgency": "high"}]
        }

        with patch.object(self.agent, 'load_jules_instructions', return_value="Instructions") as mock_load:
            result = self.agent.generate_roadmap_instructions("repo1", analysis)
            self.assertEqual(result, "Instructions")
            _args, kwargs = mock_load.call_args
            self.assertIn("priorities", kwargs['variables'])
            self.assertIn("- Bugs: 5 items (urgency: high)", kwargs['variables']['priorities'])

    def test_persona_mission(self):
         with patch.object(self.agent, 'get_instructions_section', return_value="Content"):
             self.assertEqual(self.agent.persona, "Content")
             self.assertEqual(self.agent.mission, "Content")
