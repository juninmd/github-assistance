"""Tests for the Secret Remover Agent."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from src.agents.secret_remover.agent import SecretRemoverAgent
from src.agents.secret_remover.ai_analyzer import analyze_finding
from src.agents.secret_remover.telegram_summary import (
    build_finding_message,
    get_finding_buttons,
    send_finding_notification,
)
from src.agents.secret_remover.utils import (
    _get_remote_url,
    apply_allowlist_locally,
    build_commit_url,
    build_file_line_url,
    build_repo_url,
    get_original_line,
    remove_secret_from_history,
)


class TestAnalyzeFinding(unittest.TestCase):
    def test_delegates_to_structured_classifier(self):
        ai_client = MagicMock()
        ai_client.classify_secret_finding.return_value = {
            "action": "IGNORE",
            "reason": "test fixture",
        }

        finding = {
            "rule_id": "generic-api-key",
            "file": "test.env",
            "line": 1,
            "redacted_context": "> 1: API_KEY = \"<redacted>\"",
        }
        result = analyze_finding(finding, ai_client)

        self.assertEqual(result["action"], "IGNORE")
        ai_client.classify_secret_finding.assert_called_once_with(
            finding=finding,
            redacted_context=finding["redacted_context"],
        )


class TestUrlBuilders(unittest.TestCase):
    def test_build_commit_url(self):
        url = build_commit_url("owner/repo", "abc123")
        self.assertEqual(url, "https://github.com/owner/repo/commit/abc123")

    def test_build_file_line_url(self):
        url = build_file_line_url("owner/repo", "abc123", "src/main.py", 42)
        self.assertEqual(url, "https://github.com/owner/repo/blob/abc123/src/main.py#L42")

    def test_build_repo_url(self):
        url = build_repo_url("owner/repo")
        self.assertEqual(url, "https://github.com/owner/repo")


class TestGetOriginalLine(unittest.TestCase):
    def test_returns_line_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.py"
            f.write_text("line1\nline2\nAPI_KEY=secret\n", encoding="utf-8")
            result = get_original_line(tmpdir, {"file": "test.py", "line": 3})
        self.assertEqual(result, "API_KEY=secret")

    def test_missing_file_returns_empty(self):
        result = get_original_line("/nonexistent", {"file": "x.py", "line": 1})
        self.assertEqual(result, "")

    def test_missing_file_path_returns_empty(self):
        result = get_original_line("/tmp", {"file": "", "line": 1})
        self.assertEqual(result, "")


class TestApplyAllowlistLocally(unittest.TestCase):
    @patch("src.agents.secret_remover.utils.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            findings = [{"rule_id": "aws-key", "file": "config.py"}]
            result = apply_allowlist_locally("owner/repo", findings, tmpdir, "token", print)
        self.assertTrue(result)

    @patch("src.agents.secret_remover.utils.subprocess.run")
    def test_failure_on_git_error(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, "git commit", stderr="error")
        with tempfile.TemporaryDirectory() as tmpdir:
            findings = [{"rule_id": "aws-key", "file": "config.py"}]
            result = apply_allowlist_locally("owner/repo", findings, tmpdir, "token", print)
        self.assertFalse(result)


class TestRemoveSecretFromHistory(unittest.TestCase):
    @patch("src.agents.secret_remover.utils._get_remote_url", return_value="https://github.com/owner/repo.git")
    @patch("src.agents.secret_remover.utils.subprocess.run")
    def test_success(self, mock_run, _mock_remote):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = remove_secret_from_history(
            "owner/repo", {"file": "secrets.env"}, "/tmp/repo", print
        )
        self.assertTrue(result)
        # Verify remote re-add call is present
        remote_add_calls = [
            c for c in mock_run.call_args_list
            if c[0][0][:3] == ["git", "remote", "add"]
        ]
        self.assertEqual(len(remote_add_calls), 1)

    @patch("src.agents.secret_remover.utils._get_remote_url", return_value="https://github.com/owner/repo.git")
    @patch("src.agents.secret_remover.utils.subprocess.run")
    def test_filter_repo_failure(self, mock_run, _mock_remote):
        mock_run.return_value = MagicMock(returncode=1, stderr="fatal error")
        result = remove_secret_from_history(
            "owner/repo", {"file": "secrets.env"}, "/tmp/repo", print
        )
        self.assertFalse(result)

    def test_missing_file_returns_false(self):
        result = remove_secret_from_history("owner/repo", {"file": ""}, "/tmp/repo", print)
        self.assertFalse(result)

    @patch("src.agents.secret_remover.utils._get_remote_url", return_value="")
    def test_no_remote_url_returns_false(self, _mock_remote):
        result = remove_secret_from_history(
            "owner/repo", {"file": "secrets.env"}, "/tmp/repo", print
        )
        self.assertFalse(result)

    @patch("src.agents.secret_remover.utils._get_remote_url", return_value="https://github.com/owner/repo.git")
    @patch("src.agents.secret_remover.utils.subprocess.run")
    def test_timeout_returns_false(self, mock_run, _mock_remote):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git-filter-repo", timeout=300)
        result = remove_secret_from_history(
            "owner/repo", {"file": "secrets.env"}, "/tmp/repo", print
        )
        self.assertFalse(result)


class TestGetRemoteUrl(unittest.TestCase):
    @patch("src.agents.secret_remover.utils.subprocess.run")
    def test_returns_url(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://github.com/owner/repo.git\n"
        )
        url = _get_remote_url("/tmp/repo")
        self.assertEqual(url, "https://github.com/owner/repo.git")

    @patch("src.agents.secret_remover.utils.subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        url = _get_remote_url("/tmp/repo")
        self.assertEqual(url, "")

    @patch("src.agents.secret_remover.utils.subprocess.run")
    def test_returns_empty_on_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        url = _get_remote_url("/tmp/repo")
        self.assertEqual(url, "")


class TestTelegramSummary(unittest.TestCase):
    def setUp(self):
        self.telegram = MagicMock()
        self.telegram.escape = lambda t: t.replace("_", "\\_") if t else ""

    def test_build_finding_message_remove(self):
        finding = {"file": "config.py", "line": 10, "_reason": "real token"}
        msg = build_finding_message(
            repo_name="owner/repo",
            finding=finding,
            original_line="API_KEY=real_token",
            action="REMOVE_FROM_HISTORY",
            commit_url="https://github.com/owner/repo/commit/abc",
            file_line_url="https://github.com/owner/repo/blob/abc/config.py#L10",
            repo_url="https://github.com/owner/repo",
            telegram=self.telegram,
        )
        self.assertIn("Removida do Histórico", msg)
        self.assertIn("real token", msg)

    def test_build_finding_message_ignore(self):
        finding = {"file": "test.py", "line": 1, "_reason": "fixture"}
        msg = build_finding_message(
            repo_name="owner/repo",
            finding=finding,
            original_line="API_KEY=fake",
            action="IGNORE",
            commit_url="https://github.com/owner/repo/commit/abc",
            file_line_url="https://github.com/owner/repo/blob/abc/test.py#L1",
            repo_url="https://github.com/owner/repo",
            telegram=self.telegram,
        )
        self.assertIn("Falso Positivo", msg)

    def test_get_finding_buttons_structure(self):
        buttons = get_finding_buttons(
            "https://github.com/owner/repo",
            "https://github.com/owner/repo/commit/abc",
            "https://github.com/owner/repo/blob/abc/f.py#L1",
        )
        self.assertEqual(len(buttons), 2)
        self.assertEqual(len(buttons[0]), 2)

    def test_send_finding_notification_calls_telegram(self):
        finding = {"file": "f.py", "line": 1, "_reason": "ok", "commit": "abc"}
        send_finding_notification(
            telegram=self.telegram,
            repo_name="owner/repo",
            finding=finding,
            action="IGNORE",
            original_line="line content",
            commit_url="https://github.com/owner/repo/commit/abc",
            file_line_url="https://github.com/owner/repo/blob/abc/f.py#L1",
            repo_url="https://github.com/owner/repo",
        )
        self.telegram.send_message.assert_called_once()


class TestSecretRemoverAgent(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock()
        self.github_client = MagicMock()
        self.allowlist = MagicMock()
        self.telegram = MagicMock()
        self.telegram.escape = lambda t: t.replace("_", "\\_") if t else ""

        self.agent = SecretRemoverAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            telegram=self.telegram,
            target_owner="testowner",
            ai_provider="gemini",
            ai_model="gemini-2.5-flash",
            ai_config={"api_key": "fake"},
        )
        self.agent.get_instructions_section = MagicMock(return_value="Dummy")

    @patch("glob.glob")
    def test_find_latest_results_no_files(self, mock_glob):
        mock_glob.return_value = []
        self.assertIsNone(self.agent._find_latest_results())

    @patch("builtins.open", mock_open(read_data='{"repositories_with_findings": []}'))
    @patch("glob.glob")
    def test_find_latest_results_returns_latest(self, mock_glob):
        mock_glob.return_value = [
            "results/security-scanner_20260101.json",
            "results/security-scanner_20260201.json",
        ]
        result = self.agent._find_latest_results()
        self.assertIsNotNone(result)
        self.assertIn("repositories_with_findings", result or {})

    @patch("builtins.open", mock_open(read_data='{"repositories_with_findings": []}'))
    @patch("glob.glob")
    def test_find_latest_results_searches_repo_root_when_cwd_has_none(self, mock_glob):
        mock_glob.side_effect = [[], ["results/security-scanner_20260201.json"]]
        result = self.agent._find_latest_results()
        self.assertIsNotNone(result)
        self.assertIn("repositories_with_findings", result or {})
        self.assertEqual(mock_glob.call_count, 2)

    @patch("builtins.open", mock_open(read_data='not json'))
    @patch("glob.glob")
    def test_find_latest_results_skips_malformed_json(self, mock_glob):
        mock_glob.return_value = [
            "results/security-scanner_20260301.json",
            "results/security-scanner_20260302.json",
        ]
        mocked_open = mock_open()
        mocked_open.side_effect = [
            mock_open(read_data='not json').return_value,
            mock_open(read_data='{"repositories_with_findings": []}').return_value,
        ]
        with patch("builtins.open", mocked_open):
            result = self.agent._find_latest_results()
        self.assertIsNotNone(result)
        self.assertIn("repositories_with_findings", result or {})

    @patch.object(SecretRemoverAgent, "_find_latest_results", return_value=None)
    def test_run_no_results_sends_error(self, _mock_find):
        result = self.agent.run()
        self.assertIn("error", result)
        self.telegram.send_message.assert_called_once()

    @patch.object(SecretRemoverAgent, "_process_repo")
    @patch.object(SecretRemoverAgent, "_find_latest_results")
    def test_run_processes_repos(self, mock_find, mock_process):
        mock_find.return_value = {
            "repositories_with_findings": [
                {"repository": "owner/repo1", "findings": [{"rule_id": "r1"}], "default_branch": "main"},
                {"repository": "owner/repo2", "findings": [{"rule_id": "r2"}], "default_branch": "master"},
            ]
        }
        mock_process.return_value = {"repository": "owner/repo1", "ignored": 1, "to_remove": 0, "actions": []}
        result = self.agent.run()
        self.assertEqual(result["total_repos_processed"], 2)
        self.assertEqual(mock_process.call_count, 2)

    @patch.object(SecretRemoverAgent, "_process_repo", side_effect=RuntimeError("boom"))
    @patch.object(SecretRemoverAgent, "_find_latest_results")
    def test_run_handles_repo_error(self, mock_find, _mock_process):
        mock_find.return_value = {
            "repositories_with_findings": [
                {"repository": "owner/repo1", "findings": [{"rule_id": "r1"}], "default_branch": "main"},
            ]
        }
        result = self.agent.run()
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["error"], "boom")

    @patch.object(SecretRemoverAgent, "_build_redacted_context", return_value="> 1: token = <redacted>")
    @patch.object(SecretRemoverAgent, "_create_allowlist_session", return_value=True)
    @patch.object(SecretRemoverAgent, "_create_removal_session")
    @patch("src.agents.secret_remover.agent.send_finding_notification")
    @patch("src.agents.secret_remover.agent.analyze_finding")
    @patch("src.agents.secret_remover.agent.subprocess.run")
    @patch("src.agents.secret_remover.agent.os.getenv", return_value="fake-token")
    def test_process_repo_all_ignore(
        self, _mock_env, mock_subprocess, mock_analyze,
        mock_notify, mock_remove_session, mock_allowlist_session, _mock_context,
    ):
        mock_subprocess.return_value = MagicMock(returncode=0)
        mock_analyze.return_value = {"action": "IGNORE", "reason": "test data"}

        findings = [
            {"rule_id": "rule-1", "file": "test.env", "line": 1, "commit": "abc"},
            {"rule_id": "rule-2", "file": "fake.py", "line": 2, "commit": "def"},
        ]
        result = self.agent._process_repo("owner/repo", findings, "main")

        self.assertEqual(result["ignored"], 2)
        self.assertEqual(result["to_remove"], 0)
        mock_remove_session.assert_not_called()
        mock_allowlist_session.assert_called_once()
        self.assertEqual(mock_notify.call_count, 2)

    @patch.object(SecretRemoverAgent, "_build_redacted_context", return_value="> 4: api_key = <redacted>")
    @patch.object(SecretRemoverAgent, "_create_allowlist_session")
    @patch.object(SecretRemoverAgent, "_create_removal_session", return_value=True)
    @patch("src.agents.secret_remover.agent.send_finding_notification")
    @patch("src.agents.secret_remover.agent.analyze_finding")
    @patch("src.agents.secret_remover.agent.subprocess.run")
    @patch("src.agents.secret_remover.agent.os.getenv", return_value="fake-token")
    def test_process_repo_remove_from_history(
        self, _mock_env, mock_subprocess, mock_analyze,
        mock_notify, mock_remove_session, mock_allowlist_session, _mock_context,
    ):
        mock_subprocess.return_value = MagicMock(returncode=0)
        mock_analyze.return_value = {"action": "REMOVE_FROM_HISTORY", "reason": "real token"}

        findings = [{"rule_id": "aws-key", "file": "config.py", "line": 4, "commit": "abc"}]
        result = self.agent._process_repo("owner/repo", findings, "main")

        self.assertEqual(result["to_remove"], 1)
        self.assertEqual(result["ignored"], 0)
        mock_remove_session.assert_called_once()
        mock_allowlist_session.assert_not_called()
        self.assertEqual(result["actions"][0]["status"], "REMOVED")
        mock_notify.assert_called_once()

    @patch.object(SecretRemoverAgent, "_build_redacted_context", return_value="> 1: token = <redacted>")
    @patch.object(SecretRemoverAgent, "_create_removal_session", return_value=False)
    @patch("src.agents.secret_remover.agent.send_finding_notification")
    @patch("src.agents.secret_remover.agent.analyze_finding")
    @patch("src.agents.secret_remover.agent.subprocess.run")
    @patch("src.agents.secret_remover.agent.os.getenv", return_value="fake-token")
    def test_process_repo_removal_error(
        self, _mock_env, mock_subprocess, mock_analyze,
        mock_notify, _mock_remove_session, _mock_context,
    ):
        mock_subprocess.return_value = MagicMock(returncode=0)
        mock_analyze.return_value = {"action": "REMOVE_FROM_HISTORY", "reason": "real token"}

        result = self.agent._process_repo(
            "owner/repo", [{"rule_id": "aws-key", "file": "config.py", "line": 1, "commit": "abc"}], "main"
        )
        self.assertEqual(result["actions"][0]["status"], "ERROR")

    @patch("src.agents.secret_remover.agent.analyze_finding", return_value={"action": "IGNORE", "reason": "ok"})
    @patch("src.agents.secret_remover.agent.send_finding_notification")
    @patch.object(SecretRemoverAgent, "_find_latest_results")
    def test_run_respects_max_findings_limit(self, mock_find, _mock_notify, _mock_analyze):
        big_findings = [
            {"rule_id": "r", "file": f"f{i}.py", "line": i, "commit": "a"} for i in range(200)
        ]
        repos = [
            {"repository": f"owner/repo{i}", "findings": big_findings, "default_branch": "main"}
            for i in range(5)
        ]
        mock_find.return_value = {"repositories_with_findings": repos}

        with patch.object(
            self.agent, "_process_repo",
            return_value={"ignored": 0, "to_remove": 0, "actions": []},
        ) as mock_process:
            result = self.agent.run()

        total_findings_analysed = sum(len(call.args[1]) for call in mock_process.call_args_list)
        from src.agents.secret_remover.agent import _MAX_FINDINGS_PER_RUN
        self.assertLessEqual(total_findings_analysed, _MAX_FINDINGS_PER_RUN)
        self.assertEqual(len(result["actions_taken"]), len(mock_process.call_args_list))

    def test_build_redacted_context_masks_long_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir)
            target_file = repo_dir / "app.env"
            target_file.write_text(
                "DEBUG=true\nAPI_KEY=supersecretvalue123456\nNAME=demo\n",
                encoding="utf-8",
            )
            context = self.agent._build_redacted_context(
                str(repo_dir), {"file": "app.env", "line": 2},
            )
        self.assertIn("<redacted>", context)
        self.assertNotIn("supersecretvalue123456", context)

    def test_persona(self):
        with patch.object(self.agent, "get_instructions_section", return_value="Test Persona"):
            self.assertEqual(self.agent.persona, "Test Persona")

    def test_mission(self):
        with patch.object(self.agent, "get_instructions_section", return_value="Test Mission"):
            self.assertEqual(self.agent.mission, "Test Mission")

    def test_create_allowlist_session_no_clone_dir(self):
        result = self.agent._create_allowlist_session("repo", [{"rule_id": "r1", "file": "f1"}], "main")
        self.assertFalse(result)

    def test_create_removal_session_no_clone_dir(self):
        result = self.agent._create_removal_session("repo", {"file": "f1"}, "")
        self.assertFalse(result)

    @patch("src.agents.secret_remover.utils.subprocess.run")
    def test_create_allowlist_session_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.agent._create_allowlist_session(
                "owner/repo", [{"rule_id": "r1", "file": "f1"}], "main", tmpdir, "token"
            )
        self.assertTrue(result)

    @patch("src.agents.secret_remover.utils.subprocess.run")
    def test_create_removal_session_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = self.agent._create_removal_session(
            "owner/repo", {"file": "config.py"}, "/tmp/repo"
        )
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
