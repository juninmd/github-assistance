import subprocess
import unittest
from unittest.mock import MagicMock, patch

from src.agents.opencode_runner import OpencodeRunner, _redact


def _patch_tmpdir(mock_tmpdir):
    """Point the patched TemporaryDirectory at a real temp dir (Windows-safe)."""
    import tempfile

    real_tmp = tempfile.mkdtemp(prefix="opencode-runner-test-")
    mock_tmpdir.return_value.__enter__.return_value = real_tmp
    return real_tmp


class TestOpencodeRunner(unittest.TestCase):
    def setUp(self):
        self.allowlist = MagicMock()
        self.allowlist.is_allowed.return_value = True
        self.github_client = MagicMock()
        self.telegram = MagicMock()
        self.runner = OpencodeRunner(self.allowlist, MagicMock(), self.github_client, self.telegram)
        self.runner.max_attempts = 1

    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.proc_run")
    def test_run_on_repo_returns_timeout_status_when_opencode_times_out(self, mock_run, mock_tmpdir):
        _patch_tmpdir(mock_tmpdir)
        ok_result = subprocess.CompletedProcess(["git"], 0, "", "")

        def side_effect(cmd, **_kwargs):
            if "opencode" in cmd and "run" in cmd and "--model" in cmd and "ping" not in cmd:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=1200)
            return ok_result

        mock_run.side_effect = side_effect

        result = self.runner.run_on_repo("juninmd/repo", "instructions", "Title", "agent")

        self.assertEqual(result["status"], "opencode_timeout")
        self.assertIn("timed out", result["stderr"])

    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.proc_run")
    def test_run_on_repo_retries_and_opens_pr(self, mock_run, mock_tmpdir):
        _patch_tmpdir(mock_tmpdir)
        self.runner.max_attempts = 2
        ok_result = subprocess.CompletedProcess(["git"], 0, "", "")
        first_fail = subprocess.CompletedProcess(["opencode"], 1, "", "boom")
        second_ok = subprocess.CompletedProcess(["opencode"], 0, "done", "")
        commit_ok = subprocess.CompletedProcess(["git", "commit"], 0, "[main] commit", "")
        run_count = {"n": 0}

        def side_effect(cmd, **_kwargs):
            if "opencode" in cmd and "run" in cmd and "ping" not in cmd:
                run_count["n"] += 1
                return first_fail if run_count["n"] == 1 else second_ok
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
        self.assertEqual(result["model"], "litellm/cloud/llama-70b")
        opencode_run_calls = [
            call.args[0]
            for call in mock_run.call_args_list
            if "opencode" in call.args[0] and "run" in call.args[0] and call.args[0][-1] != "ping"
        ]
        models = [cmd[4] for cmd in opencode_run_calls]
        self.assertEqual(models, ["litellm/cloud/llama-70b", "litellm/cloud/llama-70b"])


class TestRedact(unittest.TestCase):
    def test_redacts_token_from_clone_url(self):
        text = "fatal: unable to access 'https://x-access-token:ghp_secretsecretsecretsecretsecretsecre@github.com/juninmd/repo.git/'"
        assert "ghp_secretsecretsecretsecretsecretsecre" not in _redact(text)
        assert "x-access-token" not in _redact(text)

    def test_redacts_raw_token_pattern(self):
        text = "token=ghp_" + "a" * 36 + " leaked in error"
        assert "ghp_" + "a" * 36 not in _redact(text)


class TestOpencodeRunnerRedactsCloneFailure(unittest.TestCase):
    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.proc_run")
    @patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_" + "a" * 36})
    def test_clone_failure_message_never_contains_token(self, mock_run, mock_tmpdir):
        _patch_tmpdir(mock_tmpdir)
        allowlist = MagicMock()
        allowlist.is_allowed.return_value = True
        runner = OpencodeRunner(allowlist, MagicMock(), MagicMock(), MagicMock())

        def side_effect(cmd, **_kwargs):
            return subprocess.CompletedProcess(
                cmd, 128, "", f"fatal: could not read from '{' '.join(cmd)}'"
            )

        mock_run.side_effect = side_effect

        result = runner.run_on_repo("juninmd/repo", "instructions", "Title", "agent")

        assert result["status"] == "clone_failed"
        assert "ghp_" + "a" * 36 not in result["error"]


if __name__ == "__main__":
    unittest.main()
