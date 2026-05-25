import os
import unittest
from unittest.mock import MagicMock, patch

from scripts.generate_missing_docs import (
    generate_agents_content,
    generate_content,
    generate_readme_content,
    main,
)


class TestGenerateContent(unittest.TestCase):
    @patch("scripts.generate_missing_docs.requests.post")
    def test_generate_content_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Generated content"}
        mock_post.return_value = mock_response
        result = generate_content("test prompt")
        self.assertEqual(result, "Generated content")

    @patch("scripts.generate_missing_docs.requests.post")
    def test_generate_content_error(self, mock_post):
        mock_post.side_effect = Exception("Ollama error")
        result = generate_content("test prompt")
        self.assertEqual(result, "")

    @patch("scripts.generate_missing_docs.requests.post")
    def test_generate_content_http_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_post.return_value = mock_response
        result = generate_content("test prompt")
        self.assertEqual(result, "")


class TestGenerateReadmeContent(unittest.TestCase):
    @patch("scripts.generate_missing_docs.generate_content")
    def test_generate_readme_content(self, mock_gen):
        mock_gen.return_value = "# README"
        result = generate_readme_content("my-repo", "A repo", "file1\nfile2")
        self.assertEqual(result, "# README")
        prompt_arg = mock_gen.call_args[0][0]
        self.assertIn("my-repo", prompt_arg)
        self.assertIn("A repo", prompt_arg)
        self.assertIn("file1", prompt_arg)

    @patch("scripts.generate_missing_docs.generate_content")
    def test_generate_readme_content_empty_desc(self, mock_gen):
        mock_gen.return_value = "# README"
        result = generate_readme_content("my-repo", "", "files")
        self.assertEqual(result, "# README")
        prompt_arg = mock_gen.call_args[0][0]
        self.assertIn("standard software project", prompt_arg)


class TestGenerateAgentsContent(unittest.TestCase):
    @patch("scripts.generate_missing_docs.generate_content")
    def test_generate_agents_content(self, mock_gen):
        mock_gen.return_value = "# AGENTS"
        result = generate_agents_content()
        self.assertEqual(result, "# AGENTS")
        prompt_arg = mock_gen.call_args[0][0]
        self.assertIn("DRY", prompt_arg)
        self.assertIn("KISS", prompt_arg)
        self.assertIn("SOLID", prompt_arg)


class TestMainFunction(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {
            "GITHUB_TOKEN": "test-token",
            "ENABLE_AI": "true",
        }, clear=True)
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    @patch("scripts.generate_missing_docs.Github")
    def test_main_ai_disabled(self, mock_github):
        with patch.dict(os.environ, {"ENABLE_AI": "false"}, clear=True):
            main()
        mock_github.assert_not_called()

    @patch("scripts.generate_missing_docs.Github")
    def test_main_no_token(self, mock_github):
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=True):
            main()
        mock_github.assert_not_called()

    @patch("scripts.generate_missing_docs.Github")
    def test_main_skips_archived_repos(self, mock_github):
        repo = MagicMock()
        repo.archived = True
        repo.full_name = "owner/archived-repo"
        mock_user = MagicMock()
        mock_user.get_repos.return_value = [repo]
        mock_github.return_value.get_user.return_value = mock_user
        main()
        repo.get_contents.assert_not_called()

    @patch("scripts.generate_missing_docs.Github")
    def test_main_has_readme_skips_generation(self, mock_github):
        repo = MagicMock()
        repo.archived = False
        repo.full_name = "owner/repo"
        repo.name = "repo"
        repo.description = "desc"
        repo.default_branch = "main"
        repo.get_contents.return_value = MagicMock()
        mock_user = MagicMock()
        mock_user.get_repos.return_value = [repo]
        mock_github.return_value.get_user.return_value = mock_user
        main()
        repo.create_file.assert_not_called()

    @patch("scripts.generate_missing_docs.Github")
    def test_main_missing_readme_creates_it(self, mock_github):
        from github.GithubException import UnknownObjectException
        repo = MagicMock()
        repo.archived = False
        repo.full_name = "owner/repo"
        repo.name = "repo"
        repo.description = "desc"
        repo.default_branch = "main"
        repo.get_contents.side_effect = UnknownObjectException(404, {"message": "Not Found"})
        mock_user = MagicMock()
        mock_user.get_repos.return_value = [repo]
        mock_github.return_value.get_user.return_value = mock_user
        with patch("scripts.generate_missing_docs.generate_readme_content") as mock_gen_readme, \
             patch("scripts.generate_missing_docs.generate_agents_content") as mock_gen_agents:
            mock_gen_readme.return_value = "# README"
            mock_gen_agents.return_value = "# AGENTS"
            main()
            repo.create_file.assert_any_call(
                path="README.md", message="docs: create README.md via AI",
                content="# README", branch="main"
            )
            repo.create_file.assert_any_call(
                path="AGENTS.md", message="docs: create AGENTS.md via AI",
                content="# AGENTS", branch="main"
            )

    @patch("scripts.generate_missing_docs.Github")
    def test_main_empty_repo_skipped(self, mock_github):
        from github.GithubException import GithubException
        repo = MagicMock()
        repo.archived = False
        repo.full_name = "owner/repo"
        repo.name = "repo"
        repo.description = "desc"
        repo.default_branch = "main"

        def get_contents_side_effect(path):
            raise GithubException(404, {"message": "This repository is empty."})
        repo.get_contents.side_effect = get_contents_side_effect
        mock_user = MagicMock()
        mock_user.get_repos.return_value = [repo]
        mock_github.return_value.get_user.return_value = mock_user
        main()
        repo.create_file.assert_not_called()
