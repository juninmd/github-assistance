import unittest
from unittest.mock import MagicMock, patch
from src.agents.product_manager.agent import ProductManagerAgent

class TestProductManagerAgent(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.agent = ProductManagerAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

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
        with patch.object(self.agent, 'analyze_and_create_roadmap', side_effect=Exception("Failed")) as mock_analyze:
            result = self.agent.run()
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(result["failed"][0]["repository"], "repo1")

    def test_analyze_and_create_roadmap(self):
        repo_info = MagicMock()
        self.mock_github.get_repo.return_value = repo_info

        with patch.object(self.agent, 'analyze_repository', return_value={"summary": "ok", "priorities": []}) as mock_analyze_repo:
            with patch.object(self.agent, 'generate_roadmap_instructions', return_value="instructions") as mock_gen_instr:
                with patch.object(self.agent, 'create_jules_session', return_value={"id": "123"}) as mock_create_session:
                    result = self.agent.analyze_and_create_roadmap("repo1")

                    self.assertEqual(result["session_id"], "123")
                    mock_analyze_repo.assert_called()
                    mock_gen_instr.assert_called()
                    mock_create_session.assert_called()

    def test_analyze_and_create_roadmap_repo_not_found(self):
        self.mock_github.get_repo.side_effect = Exception("Not found")
        with self.assertRaises(ValueError):
            self.agent.analyze_and_create_roadmap("repo1")

    def test_analyze_repository(self):
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

        result = self.agent.analyze_repository("repo1", repo_info)

        self.assertEqual(result["total_issues"], 2)
        # Verify priorities logic
        priorities = {p['category']: p['count'] for p in result['priorities']}
        self.assertEqual(priorities["Bugs"], 1)
        self.assertEqual(priorities["Features"], 1)

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
            args, kwargs = mock_load.call_args
            self.assertIn("priorities", kwargs['variables'])
            self.assertIn("- Bugs: 5 items (urgency: high)", kwargs['variables']['priorities'])

    def test_persona_mission(self):
         with patch.object(self.agent, 'get_instructions_section', return_value="Content"):
             self.assertEqual(self.agent.persona, "Content")
             self.assertEqual(self.agent.mission, "Content")
