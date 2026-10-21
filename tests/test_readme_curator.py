import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from github.GithubException import UnknownObjectException

from src.agents.readme_curator.agent import ReadmeCuratorAgent
from src.notifications.telegram import TelegramNotifier

_GOOD_README = (
    "# My Project\n\n"
    "Um projeto que faz X de forma Y, pensado para desenvolvedores que precisam de Z. "
    "Ele resolve o problema W com uma arquitetura simples e testável, sem dependências pesadas. "
    "Esta descrição tem mais de 120 caracteres de propósito para passar na rubrica.\n\n"
    "[![CI](https://github.com/owner/repo/actions/workflows/ci.yml/badge.svg)](https://github.com/owner/repo/actions)\n"
    "[![codecov](https://codecov.io/gh/owner/repo/branch/main/graph/badge.svg)](https://codecov.io/gh/owner/repo)\n\n"
    "## Features\n\n- A\n- B\n- C\n\n"
    "## Installation\n\n```bash\npip install my-project\n```\n\n"
    "## Usage\n\n```bash\nmy-project run --help\n```\n\n"
    "## Configuration\n\n| Var | Description |\n|---|---|\n| `API_KEY` | chave |\n| `.env` | arquivo |\n\n"
    "## Architecture\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\n"
    "## Contributing\n\nVeja as instruções de desenvolvimento.\n\n"
    "## License\n\nMIT.\n"
)


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

    @staticmethod
    def _set_readme_age(repo, days):
        commit = MagicMock()
        commit.commit.committer.date = datetime.now(UTC) - timedelta(days=days)
        repo.get_commits.return_value = [commit]

    def _agent(self):
        return ReadmeCuratorAgent(
            self.jules_client, self.github_client, self.allowlist,
            telegram=self.telegram, target_owner="testuser",
        )

    def test_stale_readme_triggers_update(self):
        agent = self._agent()
        repo = MagicMock(full_name="owner/repo", default_branch="main", archived=False, fork=False)
        repo.get_readme.return_value = MagicMock(decoded_content=_GOOD_README.encode(), path="README.md")
        self._set_readme_age(repo, days=200)
        agent.create_opencode_task = MagicMock(return_value={"status": "task_created", "task_url": "http://pr"})

        results = {"processed": [], "skipped": [], "failed": []}
        agent._process_repository(repo, results)

        self.assertEqual(len(results["processed"]), 1)
        self.assertIn("stale", results["processed"][0]["reason"])
        self.assertIn("English", agent.create_opencode_task.call_args.kwargs["instructions"])
        repo.get_commits.assert_called_with(path="README.md")

    def test_fresh_readme_is_skipped_and_age_limit_configurable(self):
        agent = self._agent()
        repo = MagicMock(full_name="owner/repo", archived=False, fork=False)
        self._set_readme_age(repo, days=100)
        self.assertEqual(agent._readme_is_stale(repo, "README.md"), (False, ""))
        with patch.dict("os.environ", {"README_MAX_AGE_DAYS": "30"}):
            self.assertTrue(agent._readme_is_stale(repo, "README.md")[0])
        with patch.dict("os.environ", {"README_MAX_AGE_DAYS": "abc"}):
            self.assertEqual(agent._max_age_days(), 180)

    def test_history_error_and_naive_dates(self):
        agent = self._agent()
        repo = MagicMock(full_name="owner/repo")
        repo.get_commits.side_effect = RuntimeError("boom")
        self.assertEqual(agent._readme_is_stale(repo, "README.md"), (False, ""))
        commit = MagicMock()
        commit.commit.committer.date = datetime.now() - timedelta(days=400)
        repo.get_commits.side_effect = None
        repo.get_commits.return_value = [commit]
        self.assertTrue(agent._readme_is_stale(repo, "README.md")[0])

    def test_archived_and_fork_repos_are_skipped(self):
        agent = self._agent()
        for flags in ({"archived": True, "fork": False}, {"archived": False, "fork": True}):
            repo = MagicMock(full_name="owner/repo", **flags)
            results = {"processed": [], "skipped": [], "failed": []}
            agent._process_repository(repo, results)
            self.assertEqual(results["skipped"][0]["reason"], "archived_or_fork")
            repo.get_readme.assert_not_called()

    def test_readme_curator_agent_init(self):
        agent = ReadmeCuratorAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            telegram=self.telegram,
            target_owner="testuser",
        )
        self.assertFalse(agent.uses_repository_allowlist())

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

        for weak in (None, "   ", "Short readme", "a" * 400, "# Title\n## Only\n" + "a" * 400):
            needs_work, reason = agent._readme_needs_improvement(weak)
            self.assertTrue(needs_work, weak)
            self.assertIn("score", reason)

        needs_work, reason = agent._readme_needs_improvement(_GOOD_README)
        self.assertFalse(needs_work, reason)
        self.assertEqual(reason, "")

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
        mock_repo.archived = False
        mock_repo.fork = False
        self._set_readme_age(mock_repo, days=10)
        self.github_client.get_repo.return_value = mock_repo
        agent.get_allowed_repositories = MagicMock(return_value=["owner/repo"])

        # Case 1: README already good
        mock_readme = MagicMock()
        mock_readme.decoded_content = _GOOD_README.encode("utf-8")
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
