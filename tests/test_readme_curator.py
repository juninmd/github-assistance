import unittest
from unittest.mock import MagicMock, patch

from github.GithubException import UnknownObjectException

from src.agents.readme_curator.agent import ReadmeCuratorAgent
from src.notifications.telegram import TelegramNotifier


class TestReadmeCuratorAgent(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock()
        self.github_client = MagicMock()
        self.allowlist = MagicMock()
        self.allowlist.list_repositories.return_value = ["owner/repo"]
        self.allowlist.is_allowed.return_value = True
        self.telegram = MagicMock(spec=TelegramNotifier)
        self.telegram.escape = TelegramNotifier.escape
        self.telegram.escape_html = TelegramNotifier.escape_html

    def test_readme_curator_agent_init(self):
        agent = ReadmeCuratorAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            telegram=self.telegram,
            target_owner="testuser",
        )
        self.assertTrue(agent.uses_repository_allowlist())

        with patch.object(agent, "get_instructions_section") as mock_instr:
            mock_instr.return_value = "Content"
            self.assertEqual(agent.persona, "Content")
            self.assertEqual(agent.mission, "Content")

    def test_readme_needs_improvement(self):
        agent = ReadmeCuratorAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            telegram=self.telegram,
            target_owner="testuser",
        )

        # Empty/None
        self.assertEqual(agent._readme_needs_improvement(None), (True, "empty"))
        self.assertEqual(agent._readme_needs_improvement("   "), (True, "empty"))

        # Too short
        self.assertEqual(agent._readme_needs_improvement("Short readme"), (True, "too_short"))

        # Insufficient headers
        long_text_no_headers = "a" * 400
        self.assertEqual(agent._readme_needs_improvement(long_text_no_headers), (True, "insufficient_sections"))

        # Missing key details
        text_with_one_header = "# Title\n" + "a" * 400
        self.assertEqual(agent._readme_needs_improvement(text_with_one_header), (True, "insufficient_sections"))

        text_with_two_headers_no_keywords = "# Title\n## Features\n" + "a" * 400
        self.assertEqual(agent._readme_needs_improvement(text_with_two_headers_no_keywords), (True, "missing_key_details"))

        # High-quality README
        good_readme = (
            "# Title\n"
            "## Installation\n"
            "To install this application, please clone the repository and run the setup. "
            "Make sure you have all prerequisites installed. You can install all python dependencies using: "
            "pip install -r requirements.txt. Ensure you use python 3.12 or newer.\n"
            "## Usage\n"
            "Once installed, you can start the application by running the main entrypoint: "
            "python src/main.py. Use the --help flag to see available CLI options."
        )
        self.assertEqual(agent._readme_needs_improvement(good_readme), (False, ""))

    def test_run_workflow(self):
        agent = ReadmeCuratorAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            telegram=self.telegram,
            target_owner="testuser",
        )

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.name = "repo"
        mock_repo.default_branch = "main"
        self.github_client.get_repo.return_value = mock_repo
        agent.get_allowed_repositories = MagicMock(return_value=["owner/repo"])

        # Case 1: README already good
        mock_readme = MagicMock()
        mock_readme.decoded_content = (
            b"# Title\n"
            b"## Installation\n"
            b"To install this application, please clone the repository and run the setup. "
            b"Make sure you have all prerequisites installed. You can install all python dependencies using: "
            b"pip install -r requirements.txt. Ensure you use python 3.12 or newer.\n"
            b"## Usage\n"
            b"Once installed, you can start the application by running the main entrypoint: "
            b"python src/main.py. Use the --help flag to see available CLI options."
        )
        mock_repo.get_readme.return_value = mock_readme

        result = agent.run()
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["skipped"][0]["repository"], "owner/repo")

        # Case 2: README missing (triggers task creation)
        mock_repo.get_readme.side_effect = UnknownObjectException(404, "Not Found")
        agent.create_opencode_task = MagicMock(return_value={"status": "task_created", "task_url": "http://pr"})

        result = agent.run()
        self.assertEqual(len(result["processed"]), 1)
        self.assertEqual(result["processed"][0]["pr_url"], "http://pr")
        self.assertEqual(result["processed"][0]["reason"], "missing")
        agent.create_opencode_task.assert_called_once()

        # Case 3: Other exception checking README
        mock_repo.get_readme.side_effect = RuntimeError("disk error")
        agent.create_opencode_task.reset_mock()

        result = agent.run()
        self.assertEqual(len(result["processed"]), 1)
        self.assertEqual(result["processed"][0]["reason"], "error: RuntimeError")

        # Case 4: Exception processing repository completely
        self.github_client.get_repo.side_effect = Exception("failed repo")
        result = agent.run()
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(result["failed"][0]["error"], "failed repo")
