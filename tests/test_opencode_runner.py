import subprocess
import unittest
from unittest.mock import MagicMock, call, patch


class TestOpencodeRunnerTimeouts(unittest.TestCase):
    def setUp(self):
        from src.agents.opencode_runner import OpencodeRunner

        self.OpencodeRunner = OpencodeRunner
        # Force class-level cache so get_random_free_opencode_model never calls subprocess
        self._original_cache = OpencodeRunner._model_cache
        OpencodeRunner._model_cache = "opencode/big-pickle"

        self.allowlist = MagicMock()
        self.allowlist.is_allowed.return_value = True
        self.github_client = MagicMock()
        self.telegram = MagicMock()
        self.runner = OpencodeRunner(
            allowlist=self.allowlist,
            log_func=MagicMock(),
            github_client=self.github_client,
            telegram=self.telegram,
        )

    def tearDown(self):
        self.OpencodeRunner._model_cache = self._original_cache

    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.subprocess.run")
    def test_main_run_timeout_returns_structured_error(self, mock_run, mock_tmpdir):
        mock_tmpdir.return_value.__enter__ = lambda s: "/tmp/fake"
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

        clone_ok = MagicMock(returncode=0, stderr="")
        # clone, git config x2, git checkout, warmup, then main run -> TimeoutExpired
        mock_run.side_effect = [
            clone_ok,        # git clone
            MagicMock(),     # git config email
            MagicMock(),     # git config name
            MagicMock(),     # git checkout -b
            MagicMock(),     # warmup ping
            subprocess.TimeoutExpired(["opencode", "run"], 600),  # main run
        ]

        result = self.runner.run_on_repo("owner/repo", "do stuff", "Test Task")

        self.assertEqual(result["status"], "opencode_timeout")
        self.telegram.send_message.assert_called()

    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.subprocess.run")
    def test_main_run_not_found_returns_structured_error(self, mock_run, mock_tmpdir):
        mock_tmpdir.return_value.__enter__ = lambda s: "/tmp/fake"
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

        clone_ok = MagicMock(returncode=0, stderr="")
        mock_run.side_effect = [
            clone_ok,
            MagicMock(), MagicMock(), MagicMock(),  # git config x2, checkout
            MagicMock(),  # warmup
            FileNotFoundError("opencode not found"),  # main run
        ]

        result = self.runner.run_on_repo("owner/repo", "do stuff", "Test Task")

        self.assertEqual(result["status"], "opencode_not_found")

    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.subprocess.run")
    def test_warmup_timeout_does_not_abort_main_run(self, mock_run, mock_tmpdir):
        mock_tmpdir.return_value.__enter__ = lambda s: "/tmp/fake"
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

        clone_ok = MagicMock(returncode=0, stderr="")
        main_ok = MagicMock(returncode=0, stdout="done", stderr="")
        commit_ok = MagicMock(returncode=0, stdout="", stderr="")
        push_ok = MagicMock(returncode=0, stderr="")

        mock_run.side_effect = [
            clone_ok,
            MagicMock(), MagicMock(), MagicMock(),  # git config x2, checkout
            subprocess.TimeoutExpired(["opencode", "run", "--model", "opencode/big-pickle", "ping"], 120),  # warmup timeout
            main_ok,    # main run succeeds
            MagicMock(), # git add -A
            commit_ok,  # git commit
            push_ok,    # git push
        ]

        repo_mock = MagicMock()
        repo_mock.default_branch = "main"
        pr_mock = MagicMock()
        pr_mock.html_url = "https://github.com/owner/repo/pull/1"
        repo_mock.create_pull.return_value = pr_mock
        self.github_client.get_repo.return_value = repo_mock

        result = self.runner.run_on_repo("owner/repo", "do stuff", "Test Task")

        self.assertEqual(result["status"], "success")

    @patch("src.agents.opencode_runner.tempfile.TemporaryDirectory")
    @patch("src.agents.opencode_runner.subprocess.run")
    def test_warmup_generic_exception_does_not_abort(self, mock_run, mock_tmpdir):
        mock_tmpdir.return_value.__enter__ = lambda s: "/tmp/fake"
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

        clone_ok = MagicMock(returncode=0, stderr="")
        main_ok = MagicMock(returncode=0, stdout="done", stderr="")
        commit_ok = MagicMock(returncode=0, stdout="nothing to commit", stderr="")

        mock_run.side_effect = [
            clone_ok,
            MagicMock(), MagicMock(), MagicMock(),
            RuntimeError("opencode crashed during warmup"),
            main_ok,
            MagicMock(),  # git add
            commit_ok,    # git commit -> no changes
        ]

        result = self.runner.run_on_repo("owner/repo", "do stuff", "Test Task")

        self.assertEqual(result["status"], "no_changes")
