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
          "title": "AI Cool Project",
          "idea_description": "It does cool stuff.",
          "jules_prompt": "Build all code on master."
        }
        """
        self.agent._ai_client.generate.return_value = fake_response
        result = self.agent.generate_project_idea()
        self.assertEqual(
            result,
            {
                "repository_name": "ai-cool-project",
                "title": "AI Cool Project",
                "idea_description": "It does cool stuff.",
                "jules_prompt": "Build all code on master.",
            },
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
            patch.object(self.agent, "_ensure_master_branch") as mock_master,
            patch.object(self.agent, "_is_jules_source_available") as mock_source,
            patch.object(self.agent, "create_jules_session") as mock_session,
        ):
            mock_generate.return_value = {
                "repository_name": "My Cool-Project!!!",
                "title": "My Cool Project",
                "idea_description": "Test description.",
                "jules_prompt": "Build it via Jules.",
            }
            mock_instructions.return_value = "Project Instructions"
            repo = MagicMock()
            repo.default_branch = "master"
            mock_create.return_value = repo
            mock_master.return_value = True
            mock_source.return_value = True
            mock_session.return_value = {"id": "sess-1"}

            result = self.agent.run()

            self.assertEqual(result["status"], "session_created")
            self.assertEqual(result["repository"], "juninmd/my-cool-project")
            self.assertEqual(result["session_id"], "sess-1")
            mock_create.assert_called_once_with("my-cool-project", "Test description.")
            mock_master.assert_called_once_with(repo)
            mock_session.assert_called_once_with(
                repository="juninmd/my-cool-project",
                instructions="Project Instructions",
                title="Initial implementation for My Cool Project",
                base_branch="master",
            )
            self.mock_allowlist.add_repository.assert_called_once_with("juninmd/my-cool-project")

    def test_run_fails_when_jules_source_missing(self):
        with (
            patch.object(self.agent, "generate_project_idea") as mock_generate,
            patch.object(self.agent, "load_jules_instructions") as mock_instructions,
            patch.object(self.agent, "_create_github_repo") as mock_create,
            patch.object(self.agent, "_ensure_master_branch") as mock_master,
            patch.object(self.agent, "_is_jules_source_available") as mock_source,
            patch.object(self.agent, "create_jules_session") as mock_session,
        ):
            mock_generate.return_value = {
                "repository_name": "repo",
                "idea_description": "desc",
                "jules_prompt": "Build code.",
            }
            mock_instructions.return_value = "instructions"
            mock_create.return_value = MagicMock()
            mock_master.return_value = True
            mock_source.return_value = False

            result = self.agent.run()

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reason"], "jules_source_missing")
            mock_session.assert_not_called()

    def test_is_jules_source_available(self):
        self.mock_jules_client.get_source_name.return_value = "sources/github/juninmd/repo"
        self.mock_jules_client.list_sources.return_value = [
            {"name": "sources/github/juninmd/other"},
            {"name": "sources/github/juninmd/repo"},
        ]

        self.assertTrue(self.agent._is_jules_source_available("juninmd/repo"))

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
            mock_generate.return_value = {
                "repository_name": "repo",
                "idea_description": "desc",
                "jules_prompt": "Build code.",
            }
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

    def test_ensure_master_branch_creates_and_sets_default(self):
        repo = MagicMock()
        repo.default_branch = "main"
        main_ref = MagicMock()
        main_ref.object.sha = "abc123"
        repo.get_git_ref.return_value = main_ref

        self.assertTrue(self.agent._ensure_master_branch(repo))

        repo.get_git_ref.assert_called_once_with("heads/main")
        repo.create_git_ref.assert_called_once_with("refs/heads/master", "abc123")
        repo.edit.assert_called_once_with(default_branch="master")

    def test_create_roadmap_backlog_creates_labeled_issues(self):
        repo = MagicMock()
        issue1, issue2 = MagicMock(), MagicMock()
        issue1.html_url = "https://github.com/juninmd/repo/issues/1"
        issue2.html_url = "https://github.com/juninmd/repo/issues/2"
        repo.create_issue.side_effect = [issue1, issue2]
        repo.get_labels.return_value = []

        urls = self.agent._create_roadmap_backlog(repo, ["Add login", "Add dashboard"])

        self.assertEqual(urls, [issue1.html_url, issue2.html_url])
        self.assertEqual(repo.create_issue.call_count, 2)
        first_call_kwargs = repo.create_issue.call_args_list[0].kwargs
        self.assertEqual(first_call_kwargs["labels"], ["roadmap", "jules"])
        self.assertIn("## Objective", first_call_kwargs["body"])
        second_call_kwargs = repo.create_issue.call_args_list[1].kwargs
        self.assertEqual(second_call_kwargs["labels"], ["roadmap"])
        self.assertEqual(repo.create_label.call_count, 2)  # roadmap + jules labels

    def test_create_roadmap_backlog_empty_is_noop(self):
        repo = MagicMock()
        self.assertEqual(self.agent._create_roadmap_backlog(repo, []), [])
        repo.create_issue.assert_not_called()

    def test_create_roadmap_backlog_survives_issue_creation_failure(self):
        repo = MagicMock()
        repo.get_labels.return_value = []
        repo.create_issue.side_effect = Exception("rate limited")

        urls = self.agent._create_roadmap_backlog(repo, ["Add login"])

        self.assertEqual(urls, [])

    def test_ensure_master_branch_noop_when_already_master(self):
        repo = MagicMock()
        repo.default_branch = "master"

        self.assertTrue(self.agent._ensure_master_branch(repo))

        repo.create_git_ref.assert_not_called()
        repo.edit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
