import json
import unittest
from unittest.mock import MagicMock, patch

from github import GithubException

from src.agents.project_creator.agent import ProjectCreatorAgent


class TestProjectCreatorAgent(unittest.TestCase):
    def setUp(self):
        self.mock_jules_client = MagicMock()
        self.mock_github_client = MagicMock()
        self.mock_allowlist = MagicMock()

        # Prevent default AI client initialization, we'll mock it
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
        # Successful AI generation
        fake_response = '''Here is your project idea:
        {
          "repository_name": "ai-cool-project",
          "idea_description": "It does cool stuff."
        }
        '''
        self.agent._ai_client.generate.return_value = fake_response

        result = self.agent.generate_project_idea()
        self.assertEqual(result, {
            "repository_name": "ai-cool-project",
            "idea_description": "It does cool stuff."
        })

    def test_generate_project_idea_no_json(self):
        self.agent._ai_client.generate.return_value = "No JSON here."
        result = self.agent.generate_project_idea()
        self.assertIsNone(result)

    def test_generate_project_idea_invalid_json(self):
        self.agent._ai_client.generate.return_value = '{"repository_name": "foo", "idea_description": "bar"'
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
        # 1. Mock generate_project_idea
        with patch.object(self.agent, "generate_project_idea") as mock_generate:
            mock_generate.return_value = {
                "repository_name": "My Cool-Project!!!",
                "idea_description": "Test description."
            }

            # 2. Mock repository check (404 means it doesn't exist)
            self.mock_github_client.get_repo.side_effect = GithubException(404, {"message": "Not Found"})

            # 3. Mock create repository
            mock_user = MagicMock()
            self.mock_github_client.g.get_user.return_value = mock_user
            mock_repo = MagicMock()
            mock_repo.default_branch = "master"
            mock_user.create_repo.return_value = mock_repo

            # 4. Mock Jules session
            with patch.object(self.agent, "load_jules_instructions") as mock_load_instructions:
                mock_load_instructions.return_value = "Jules Instructions"
                with patch.object(self.agent, "create_jules_session") as mock_create_session:
                    mock_create_session.return_value = {"id": "session-123"}

                    result = self.agent.run()

                    self.assertEqual(result["status"], "success")
                    self.assertEqual(result["repository"], "juninmd/my-cool-project")
                    self.assertEqual(result["session_id"], "session-123")

                    mock_user.create_repo.assert_called_once_with(
                        name="my-cool-project",
                        description="Test description.",
                        private=True,
                        auto_init=True,
                    )
                    self.mock_allowlist.add_repository.assert_called_once_with("juninmd/my-cool-project")
                    mock_create_session.assert_called_once_with(
                        repository="juninmd/my-cool-project",
                        instructions="Jules Instructions",
                        title="Initialise my-cool-project - AI Project",
                        wait_for_completion=False,
                        base_branch="master",
                    )

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

    def test_run_repo_already_exists(self):
        with patch.object(self.agent, "generate_project_idea") as mock_generate:
            mock_generate.return_value = {
                "repository_name": "existing-repo",
                "idea_description": "Test description."
            }

            # If get_repo doesn't raise, it means it exists
            self.mock_github_client.get_repo.return_value = MagicMock()

            result = self.agent.run()
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "repository_already_exists")

    def test_run_check_repo_unexpected_error(self):
        with patch.object(self.agent, "generate_project_idea") as mock_generate:
            mock_generate.return_value = {
                "repository_name": "repo",
                "idea_description": "desc"
            }
            # Unrelated API error
            self.mock_github_client.get_repo.side_effect = GithubException(500, {"message": "Server error"})

            result = self.agent.run()
            self.assertEqual(result["status"], "failed")
            self.assertIn("error_checking_repo", result["reason"])

    def test_run_create_repo_github_error(self):
        with patch.object(self.agent, "generate_project_idea") as mock_generate:
            mock_generate.return_value = {
                "repository_name": "repo",
                "idea_description": "desc"
            }
            self.mock_github_client.get_repo.side_effect = GithubException(404, {"message": "Not Found"})

            mock_user = MagicMock()
            self.mock_github_client.g.get_user.return_value = mock_user
            mock_user.create_repo.side_effect = GithubException(422, {"message": "Unprocessable Entity"})

            result = self.agent.run()
            self.assertEqual(result["status"], "failed")
            self.assertIn("repo_creation_failed", result["reason"])

    def test_run_create_repo_unexpected_error(self):
        with patch.object(self.agent, "generate_project_idea") as mock_generate:
            mock_generate.return_value = {
                "repository_name": "repo",
                "idea_description": "desc"
            }
            self.mock_github_client.get_repo.side_effect = GithubException(404, {"message": "Not Found"})

            mock_user = MagicMock()
            self.mock_github_client.g.get_user.return_value = mock_user
            mock_user.create_repo.side_effect = Exception("Network dropped")

            result = self.agent.run()
            self.assertEqual(result["status"], "failed")
            self.assertIn("Network dropped", result["reason"])

    def test_run_unexpected_exception(self):
        with patch.object(self.agent, "generate_project_idea") as mock_generate:
            mock_generate.side_effect = Exception("System Crash")
            result = self.agent.run()
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"], "System Crash")

if __name__ == '__main__':
    unittest.main()
