import unittest
from unittest.mock import MagicMock, patch

from github import GithubException

from src.agents.project_creator.agent import ProjectCreatorAgent


class TestProjectCreatorAgent(unittest.TestCase):
    def setUp(self):
        self.mock_jules_client = MagicMock()
        self.mock_github_client = MagicMock()
        self.mock_allowlist = MagicMock()

        with patch("src.agents.project_creator.agent.get_ai_client") as mock_get_ai:
            self.mock_ai_client = MagicMock()
            mock_get_ai.return_value = self.mock_ai_client
            self.agent = ProjectCreatorAgent(
                jules_client=self.mock_jules_client,
                github_client=self.mock_github_client,
                allowlist=self.mock_allowlist,
            )

    def test_properties(self):
        with patch.object(self.agent, "get_instructions_section") as mock_get:
            mock_get.return_value = "Mock Persona"
            self.assertEqual(self.agent.persona, "Mock Persona")
            mock_get.assert_called_with("## Persona")

        with patch.object(self.agent, "get_instructions_section") as mock_get:
            mock_get.return_value = "Mock Mission"
            self.assertEqual(self.agent.mission, "Mock Mission")
            mock_get.assert_called_with("## Mission")

    def test_generate_project_idea_success(self):
        fake_response = """Here is your project idea:
        {
          "repository_name": "ai-cool-project",
          "idea_description": "It does cool stuff."
        }
        """
        self.agent._ai_client.generate.return_value = fake_response
        result = self.agent.generate_project_idea()
        self.assertEqual(
            result,
            {"repository_name": "ai-cool-project", "idea_description": "It does cool stuff."},
        )

    def test_generate_project_idea_no_json(self):
        self.agent._ai_client.generate.return_value = "No JSON here."
        result = self.agent.generate_project_idea()
        self.assertIsNone(result)

    def test_generate_project_idea_invalid_json(self):
        self.agent._ai_client.generate.return_value = (
            '{"repository_name": "foo", "idea_description": "bar"'
        )
        result = self.agent.generate_project_idea()
        self.assertIsNone(result)

    def test_generate_project_idea_ai_failure(self):
        self.agent._ai_client.generate.side_effect = Exception("AI ded")
        result = self.agent.generate_project_idea()
        self.assertIsNone(result)

    def test_generate_project_idea_no_client(self):
        self.agent._ai_client = None
        result = self.agent.generate_project_idea()
        self.assertIsNone(result)

    def test_run_success(self):
        with (
            patch.object(self.agent, "generate_project_idea") as mock_generate,
            patch.object(self.agent, "load_jules_instructions") as mock_instructions,
            patch.object(self.agent, "_create_github_repo") as mock_create,
            patch.object(self.agent, "create_jules_session") as mock_session,
        ):
            mock_generate.return_value = {
                "repository_name": "My Cool-Project!!!",
                "idea_description": "Test description.",
            }
            mock_instructions.return_value = "Project Instructions"
            repo = MagicMock()
            repo.default_branch = "main"
            mock_create.return_value = repo
            mock_session.return_value = {"id": "sess-1"}

            result = self.agent.run()

            self.assertEqual(result["status"], "session_created")
            self.assertEqual(result["repository"], "juninmd/my-cool-project")
            self.assertEqual(result["session_id"], "sess-1")
            mock_create.assert_called_once_with("my-cool-project", "Test description.")
            mock_session.assert_called_once_with(
                repository="juninmd/my-cool-project",
                instructions="Project Instructions",
                title="Initial implementation for my-cool-project",
                base_branch="main",
            )
            self.mock_allowlist.add_repository.assert_called_once_with("juninmd/my-cool-project")

    def test_run_idea_generation_fails(self):
        with patch.object(self.agent, "generate_project_idea") as mock_generate:
            mock_generate.return_value = None
            result = self.agent.run()
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reason"], "could_not_generate_idea")

    def test_run_idea_missing_fields(self):
        with patch.object(self.agent, "generate_project_idea") as mock_generate:
            mock_generate.return_value = {"repository_name": "foo"}
            result = self.agent.run()
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reason"], "invalid_idea_format")

    def test_run_create_repo_fails(self):
        with (
            patch.object(self.agent, "generate_project_idea") as mock_generate,
            patch.object(self.agent, "load_jules_instructions") as mock_instructions,
            patch.object(self.agent, "_create_github_repo") as mock_create,
            patch.object(self.agent, "create_jules_session") as mock_session,
        ):
            mock_generate.return_value = {"repository_name": "repo", "idea_description": "desc"}
            mock_instructions.return_value = "instructions"
            mock_create.return_value = None

            result = self.agent.run()

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reason"], "repo_creation_failed")
            mock_session.assert_not_called()

    def test_run_unexpected_exception(self):
        with patch.object(self.agent, "generate_project_idea") as mock_generate:
            mock_generate.side_effect = Exception("System Crash")
            result = self.agent.run()
            self.assertEqual(result["status"], "failed")
            self.assertNotIn("error", result)

    def test_create_github_repo_github_error(self):
        mock_user = MagicMock()
        mock_user.login = "juninmd"
        self.mock_github_client.g.get_user.return_value = mock_user
        mock_user.create_repo.side_effect = GithubException(
            422, {"message": "Unprocessable Entity"}
        )

        result = self.agent._create_github_repo("repo", "desc")
        self.assertIsNone(result)

    def test_create_github_repo_unexpected_error(self):
        mock_user = MagicMock()
        mock_user.login = "juninmd"
        self.mock_github_client.g.get_user.return_value = mock_user
        mock_user.create_repo.side_effect = Exception("Network dropped")

        result = self.agent._create_github_repo("repo", "desc")
        self.assertIsNone(result)

    def test_create_github_repo_sets_autonomous_description(self):
        mock_user = MagicMock()
        mock_user.login = "juninmd"
        self.mock_github_client.g.get_user.return_value = mock_user
        mock_repo = MagicMock()
        mock_user.create_repo.return_value = mock_repo

        self.agent._create_github_repo("repo", "A cool project.")

        call_kwargs = mock_user.create_repo.call_args
        description = call_kwargs[1]["description"] if call_kwargs[1] else call_kwargs[0][1]
        self.assertIn("github-assistance", description)
        self.assertTrue(call_kwargs[1].get("auto_init", False))


if __name__ == "__main__":
    unittest.main()
