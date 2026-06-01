import subprocess
import unittest
from datetime import UTC
from unittest.mock import MagicMock, patch

from src.agents.opencode_runner import OpencodeRunner


class TestOpencodeRunner(unittest.TestCase):
    def setUp(self):
        self.allowlist = MagicMock()
        self.allowlist.is_allowed.return_value = True
        self.github_client = MagicMock()
        self.telegram = MagicMock()
        self.runner = OpencodeRunner(self.allowlist, MagicMock(), self.github_client, self.telegram)
        self.runner.max_attempts = 1
        OpencodeRunner._model_cache = None

    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.subprocess.run")
    def test_run_on_repo_returns_timeout_status_when_opencode_times_out(
        self, mock_run, mock_tmpdir
    ):
        mock_tmpdir.return_value.__enter__.return_value = "/tmp/repo"
        model_result = subprocess.CompletedProcess(
            ["opencode", "models"], 0, "opencode/test-free", ""
        )
        ok_result = subprocess.CompletedProcess(["git"], 0, "", "")

        def side_effect(cmd, **_kwargs):
            if cmd[:2] == ["opencode", "models"]:
                return model_result
            if cmd[:3] == ["opencode", "run", "--model"] and "ping" not in cmd:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=1200)
            return ok_result

        mock_run.side_effect = side_effect

        result = self.runner.run_on_repo("juninmd/repo", "instructions", "Title", "agent")

        self.assertEqual(result["status"], "opencode_timeout")
        self.assertIn("timed out", result["stderr"])

    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.subprocess.run")
    def test_run_on_repo_retries_with_fallback_model_and_opens_pr(self, mock_run, mock_tmpdir):
        mock_tmpdir.return_value.__enter__.return_value = "/tmp/repo"
        self.runner.max_attempts = 2
        model_result = subprocess.CompletedProcess(
            ["opencode", "models"], 0, "opencode/test-free", ""
        )
        ok_result = subprocess.CompletedProcess(["git"], 0, "", "")
        first_fail = subprocess.CompletedProcess(["opencode"], 1, "", "boom")
        second_ok = subprocess.CompletedProcess(["opencode"], 0, "done", "")
        commit_ok = subprocess.CompletedProcess(["git", "commit"], 0, "[main] commit", "")

        def side_effect(cmd, **_kwargs):
            if cmd[:2] == ["opencode", "models"]:
                return model_result
            if (
                cmd[:4] == ["opencode", "run", "--model", "opencode/test-free"]
                and cmd[-1] != "ping"
            ):
                return first_fail
            if (
                cmd[:4] == ["opencode", "run", "--model", "opencode/big-pickle"]
                and cmd[-1] != "ping"
            ):
                return second_ok
            if cmd[:2] == ["git", "commit"]:
                return commit_ok
            return ok_result

        mock_run.side_effect = side_effect
        repo = MagicMock()
        repo.default_branch = "main"
        created_pr = MagicMock()
        created_pr.html_url = "https://github.com/juninmd/repo/pull/1"
        repo.create_pull.return_value = created_pr
        self.github_client.get_repo.return_value = repo

        result = self.runner.run_on_repo("juninmd/repo", "instructions", "Title", "agent")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["model"], "opencode/big-pickle")
        opencode_run_calls = [
            call.args[0]
            for call in mock_run.call_args_list
            if call.args[0][:3] == ["opencode", "run", "--model"] and call.args[0][-1] != "ping"
        ]
        models = [cmd[3] for cmd in opencode_run_calls]
        self.assertEqual(models, ["opencode/test-free", "opencode/big-pickle"])

    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.subprocess.run")
    def test_run_on_repo_performs_git_pull_before_checkout(self, mock_run, mock_tmpdir):
        mock_tmpdir.return_value.__enter__.return_value = "/tmp/repo"
        model_result = subprocess.CompletedProcess(
            ["opencode", "models"], 0, "opencode/test-free", ""
        )
        ok_result = subprocess.CompletedProcess(["git"], 0, "main\n", "")
        opencode_ok = subprocess.CompletedProcess(["opencode"], 0, "done", "")
        commit_ok = subprocess.CompletedProcess(["git", "commit"], 0, "[main] commit", "")

        def side_effect(cmd, **_kwargs):
            if cmd[:2] == ["opencode", "models"]:
                return model_result
            if cmd[:3] == ["opencode", "run", "--model"]:
                return opencode_ok
            if cmd[:2] == ["git", "commit"]:
                return commit_ok
            if cmd[:3] == ["git", "symbolic-ref", "--short"]:
                return subprocess.CompletedProcess(cmd, 0, "main\n", "")
            return ok_result

        mock_run.side_effect = side_effect
        repo = MagicMock()
        repo.default_branch = "main"
        created_pr = MagicMock()
        created_pr.html_url = "https://github.com/juninmd/repo/pull/1"
        repo.create_pull.return_value = created_pr
        self.github_client.get_repo.return_value = repo

        result = self.runner.run_on_repo("juninmd/repo", "instructions", "Title", "agent")
        self.assertEqual(result["status"], "success")

        # Let's check git pull was called on origin main
        git_calls = [
            args[0]
            for args, kwargs in mock_run.call_args_list
            if args and args[0] and args[0][0] == "git"
        ]

        pull_calls = [cmd for cmd in git_calls if cmd[:3] == ["git", "pull", "origin"]]
        self.assertEqual(len(pull_calls), 1)
        self.assertEqual(pull_calls[0][3], "main")

    def test_run_on_repo_skips_when_open_pr_exists(self):
        repo = MagicMock()
        pr = MagicMock()
        pr.title = "[agent/senior_developer] Title"
        pr.html_url = "https://github.com/juninmd/repo/pull/1"
        repo.get_pulls.return_value = [pr]
        self.github_client.get_repo.return_value = repo

        result = self.runner.run_on_repo(
            "juninmd/repo", "instructions", "Title", "senior_developer"
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "pr_already_exists")
        self.assertEqual(result["pr_url"], "https://github.com/juninmd/repo/pull/1")

    def test_run_on_repo_skips_when_recent_closed_pr_exists(self):
        from datetime import datetime, timezone

        repo = MagicMock()
        pr = MagicMock()
        pr.title = "[agent/senior_developer] Title"
        pr.html_url = "https://github.com/juninmd/repo/pull/1"
        pr.created_at = datetime.now(UTC)
        repo.get_pulls.side_effect = lambda state: [] if state == "open" else [pr]
        self.github_client.get_repo.return_value = repo

        result = self.runner.run_on_repo(
            "juninmd/repo", "instructions", "Title", "senior_developer"
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "pr_cooldown_active")


if __name__ == "__main__":
    unittest.main()
