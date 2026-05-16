"""Tests for the Secret Remover Agent."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from src.agents.secret_remover import git_utils, utils
from src.agents.secret_remover.agent import SecretRemoverAgent
from src.agents.secret_remover.ai_analyzer import analyze_finding
from src.agents.secret_remover.processor import FindingProcessor
from src.agents.secret_remover.telegram_summary import (
    build_finding_message,
    get_finding_buttons,
    send_finding_notification,
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
        url = utils.build_commit_url("owner/repo", "abc123")
        self.assertEqual(url, "https://github.com/owner/repo/commit/abc123")

    def test_build_file_line_url(self):
        url = utils.build_file_line_url("owner/repo", "abc123", "src/main.py", 42)
        self.assertEqual(url, "https://github.com/owner/repo/blob/abc123/src/main.py#L42")

    def test_build_repo_url(self):
        url = utils.build_repo_url("owner/repo")
        self.assertEqual(url, "https://github.com/owner/repo")


class TestGetOriginalLine(unittest.TestCase):
    def test_returns_line_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.py"
            f.write_text("line1\nline2\nAPI_KEY=secret\n", encoding="utf-8")
            result = utils.get_original_line(tmpdir, {"file": "test.py", "line": 3})
        self.assertEqual(result, "API_KEY=secret")


class TestGitUtils(unittest.TestCase):
    @patch("src.agents.secret_remover.git_utils.subprocess.run")
    def test_apply_allowlist_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            findings = [{"rule_id": "aws-key", "file": "config.py"}]
            result = git_utils.apply_allowlist_locally("owner/repo", findings, tmpdir, "token", print)
        self.assertTrue(result)

    @patch("src.agents.secret_remover.git_utils._get_remote_url", return_value="https://github.com/owner/repo.git")
    @patch("src.agents.secret_remover.git_utils.subprocess.run")
    def test_remove_secret_success(self, mock_run, _mock_remote):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = git_utils.remove_secret_from_history(
            "owner/repo", {"file": "secrets.env"}, "/tmp/repo", print
        )
        self.assertTrue(result)
        # Verify remote re-add call is present
        remote_add_calls = [
            c for c in mock_run.call_args_list
            if c[0][0][:3] == ["git", "remote", "add"]
        ]
        self.assertEqual(len(remote_add_calls), 1)

    @patch("src.agents.secret_remover.git_utils.subprocess.run")
    def test_get_remote_url_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://github.com/owner/repo.git\n"
        )
        url = git_utils._get_remote_url("/tmp/repo")
        self.assertEqual(url, "https://github.com/owner/repo.git")


class TestFindingProcessor(unittest.TestCase):
    def setUp(self):
        self.ai_client = MagicMock()
        self.telegram = MagicMock()
        self.telegram.escape = lambda t: t.replace("_", "\\_") if t else ""
        self.processor = FindingProcessor(self.ai_client, self.telegram, print)

    @patch("src.agents.secret_remover.processor.git_utils.remove_secret_from_history", return_value=True)
    @patch("src.agents.secret_remover.processor.git_utils.apply_allowlist_locally", return_value=True)
    @patch("src.agents.secret_remover.processor.utils.build_redacted_context", return_value="context")
    @patch("src.agents.secret_remover.processor.utils.get_original_line", return_value="line")
    @patch("src.agents.secret_remover.processor.analyze_finding")
    @patch("src.agents.secret_remover.processor.clone_repo_securely")
    @patch("src.agents.secret_remover.processor.os.getenv", return_value="token")
    def test_process_repo_mixed_actions(
        self, _mock_env, mock_clone, mock_analyze, _mock_line, _mock_context, mock_allow, mock_remove
    ):
        mock_clone.return_value = MagicMock(returncode=0)
        # First finding: remove, Second: ignore
        mock_analyze.side_effect = [
            {"action": "REMOVE_FROM_HISTORY", "reason": "leak"},
            {"action": "IGNORE", "reason": "test"},
        ]

        findings = [
            {"rule_id": "r1", "file": "f1.py", "line": 1, "commit": "c1"},
            {"rule_id": "r2", "file": "f2.py", "line": 2, "commit": "c2"},
        ]
        result = self.processor.process_repo("owner/repo", findings, "main")

        self.assertEqual(result["ignored"], 1)
        self.assertEqual(result["to_remove"], 1)
        mock_remove.assert_called_once()
        mock_allow.assert_called_once()


class TestSecretRemoverAgent(unittest.TestCase):
    def setUp(self):
        with patch("src.agents.secret_remover.agent.get_ai_client", return_value=MagicMock()):
            self.agent = SecretRemoverAgent(
                MagicMock(), MagicMock(), MagicMock(),
                telegram=MagicMock(),
                target_owner="testowner",
                ai_provider="ollama",
                ai_model="test-model"
            )

    @patch("src.agents.secret_remover.agent.utils.find_latest_results")
    @patch("src.agents.secret_remover.processor.FindingProcessor.process_repo")
    def test_run_success(self, mock_process, mock_find):
        mock_find.return_value = {
            "repositories_with_findings": [
                {"repository": "repo1", "findings": [{"id": 1}], "default_branch": "main"}
            ]
        }
        mock_process.return_value = {"repository": "repo1", "ignored": 1, "to_remove": 0, "actions": []}

        result = self.agent.run()
        self.assertEqual(result["total_repos_processed"], 1)
        self.assertEqual(len(result["actions_taken"]), 1)


if __name__ == "__main__":
    unittest.main()
