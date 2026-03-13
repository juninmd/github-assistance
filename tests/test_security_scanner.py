import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from src.agents.security_scanner.agent import SecurityScannerAgent


class TestSecurityScannerAgent(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock()
        self.github_client = MagicMock()
        self.allowlist = MagicMock()
        self.telegram = MagicMock()

        # We also need to mock `telegram.escape` because it is used directly
        def escape_mock(text):
            return text.replace("_", "\\_") if text else ""
        self.telegram.escape = escape_mock

        self.agent = SecurityScannerAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            telegram=self.telegram,
            target_owner="testowner"
        )

        # Provide a dummy get_instructions_section to avoid reading files
        self.agent.get_instructions_section = MagicMock(return_value="Dummy text")

    def test_persona_and_mission(self):
        self.assertEqual(self.agent.persona, "Dummy text")
        self.assertEqual(self.agent.mission, "Dummy text")
        self.agent.get_instructions_section.assert_any_call("## Persona")  # pyright: ignore
        self.agent.get_instructions_section.assert_any_call("## Mission")  # pyright: ignore

    @patch("subprocess.run")
    def test_ensure_gitleaks_installed_already_installed(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "v8.18.1\n"
        mock_run.return_value = mock_result

        self.assertTrue(self.agent._ensure_gitleaks_installed())
        mock_run.assert_called_once_with(["gitleaks", "version"], capture_output=True, text=True, timeout=10)

    @patch("subprocess.run")
    def test_ensure_gitleaks_installed_needs_install_success(self, mock_run):
        mock_run.side_effect = [
            subprocess.TimeoutExpired(cmd=["gitleaks", "version"], timeout=10),
            MagicMock(returncode=0)
        ]

        self.assertTrue(self.agent._ensure_gitleaks_installed())
        self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    def test_ensure_gitleaks_installed_needs_install_failure(self, mock_run):
        mock_run.side_effect = [
            FileNotFoundError(),
            MagicMock(returncode=1)
        ]

        self.assertFalse(self.agent._ensure_gitleaks_installed())
        self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    def test_ensure_gitleaks_installed_exception(self, mock_run):
        mock_run.side_effect = [
            subprocess.TimeoutExpired(cmd=["gitleaks", "version"], timeout=10),
            RuntimeError("Unknown error")
        ]
        self.assertFalse(self.agent._ensure_gitleaks_installed())

    @patch("os.getenv")
    def test_scan_repository_no_token(self, mock_getenv):
        mock_getenv.return_value = None
        result = self.agent._scan_repository("test/repo")
        self.assertEqual(result["error"], "GITHUB_TOKEN not available")
        self.assertFalse(result["scanned"])

    @patch("tempfile.TemporaryDirectory")
    @patch("os.getenv")
    @patch("subprocess.run")
    def test_scan_repository_clone_fails(self, mock_run, mock_getenv, mock_tempdir):
        mock_getenv.return_value = "fake_token"
        mock_tempdir_ctx = MagicMock()
        mock_tempdir_ctx.__enter__.return_value = "/tmp/fake"
        mock_tempdir.return_value = mock_tempdir_ctx

        mock_run.return_value = MagicMock(returncode=128)

        result = self.agent._scan_repository("test/repo")
        self.assertFalse(result["scanned"])
        self.assertIn("Clone failed", result["error"])

    @patch("tempfile.TemporaryDirectory")
    @patch("os.getenv")
    @patch("subprocess.run")
    def test_scan_repository_gitleaks_fails(self, mock_run, mock_getenv, mock_tempdir):
        mock_getenv.return_value = "fake_token"
        mock_tempdir_ctx = MagicMock()
        mock_tempdir_ctx.__enter__.return_value = "/tmp/fake"
        mock_tempdir.return_value = mock_tempdir_ctx

        mock_run.side_effect = [
            MagicMock(returncode=0), # Clone success
            MagicMock(returncode=2)  # Gitleaks internal error
        ]

        result = self.agent._scan_repository("test/repo")
        self.assertFalse(result["scanned"])
        self.assertIn("Gitleaks scan failed", result["error"])

    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("tempfile.TemporaryDirectory")
    @patch("os.getenv")
    @patch("subprocess.run")
    def test_scan_repository_success_no_leaks(self, mock_run, mock_getenv, mock_tempdir, mock_open, mock_exists):
        mock_getenv.return_value = "fake_token"
        mock_tempdir_ctx = MagicMock()
        mock_tempdir_ctx.__enter__.return_value = "/tmp/fake"
        mock_tempdir.return_value = mock_tempdir_ctx

        mock_run.side_effect = [
            MagicMock(returncode=0), # Clone success
            MagicMock(returncode=0)  # Gitleaks success (no leaks)
        ]
        mock_exists.return_value = False # No report file generated

        result = self.agent._scan_repository("test/repo")
        self.assertTrue(result["scanned"])
        self.assertEqual(result["findings"], [])
        self.assertIsNone(result["error"])

    @patch("json.load")
    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("tempfile.TemporaryDirectory")
    @patch("os.getenv")
    @patch("subprocess.run")
    def test_scan_repository_success_with_leaks(self, mock_run, mock_getenv, mock_tempdir, mock_open, mock_exists, mock_json_load):
        mock_getenv.return_value = "fake_token"
        mock_tempdir_ctx = MagicMock()
        mock_tempdir_ctx.__enter__.return_value = "/tmp/fake"
        mock_tempdir.return_value = mock_tempdir_ctx

        mock_run.side_effect = [
            MagicMock(returncode=0), # Clone success
            MagicMock(returncode=1)  # Gitleaks success (leaks found)
        ]
        mock_exists.return_value = True

        mock_json_load.return_value = [
            {"RuleID": "test-rule", "File": "/tmp/fake/repo/secret.txt", "StartLine": 1, "Commit": "abcdef123"}
        ]

        result = self.agent._scan_repository("test/repo")
        self.assertTrue(result["scanned"])
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0]["rule_id"], "test-rule")
        self.assertEqual(result["findings"][0]["file"], "secret.txt")
        self.assertIsNone(result["error"])

    @patch("json.load")
    @patch("os.path.exists")
    @patch("builtins.open")
    @patch("tempfile.TemporaryDirectory")
    @patch("os.getenv")
    @patch("subprocess.run")
    def test_scan_repository_json_error(self, mock_run, mock_getenv, mock_tempdir, mock_open, mock_exists, mock_json_load):
        mock_getenv.return_value = "fake_token"
        mock_tempdir_ctx = MagicMock()
        mock_tempdir_ctx.__enter__.return_value = "/tmp/fake"
        mock_tempdir.return_value = mock_tempdir_ctx

        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=1)
        ]
        mock_exists.return_value = True
        mock_json_load.side_effect = json.JSONDecodeError("Expecting value", "", 0)

        result = self.agent._scan_repository("test/repo")
        self.assertFalse(result["scanned"])
        self.assertIn("Failed to parse", result["error"])

    @patch("tempfile.TemporaryDirectory")
    @patch("os.getenv")
    @patch("subprocess.run")
    def test_scan_repository_timeout(self, mock_run, mock_getenv, mock_tempdir):
        mock_getenv.return_value = "fake_token"
        mock_tempdir_ctx = MagicMock()
        mock_tempdir_ctx.__enter__.return_value = "/tmp/fake"
        mock_tempdir.return_value = mock_tempdir_ctx

        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=600)

        result = self.agent._scan_repository("test/repo")
        self.assertFalse(result["scanned"])
        self.assertEqual(result["error"], "Scan timeout exceeded")

    @patch("tempfile.TemporaryDirectory")
    @patch("os.getenv")
    @patch("subprocess.run")
    def test_scan_repository_unexpected_error(self, mock_run, mock_getenv, mock_tempdir):
        mock_getenv.return_value = "fake_token"
        mock_tempdir_ctx = MagicMock()
        mock_tempdir_ctx.__enter__.return_value = "/tmp/fake"
        mock_tempdir.return_value = mock_tempdir_ctx

        mock_run.side_effect = Exception("Unexpected")

        result = self.agent._scan_repository("test/repo")
        self.assertFalse(result["scanned"])
        self.assertEqual(result["error"], "Scan error: Unexpected")

    def test_sanitize_findings(self):
        findings = [
            {
                "RuleID": "aws-access-key",
                "Description": "AWS Access Key",
                "File": "config.yml",
                "StartLine": 10,
                "Commit": "abcdef1234567890",
                "Author": "dev",
                "Date": "2023-01-01",
                "Secret": "AKIAIOSFODNN7EXAMPLE",
                "Match": "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"
            }
        ]
        sanitized = self.agent._sanitize_findings(findings)

        self.assertEqual(len(sanitized), 1)
        self.assertEqual(sanitized[0]["rule_id"], "aws-access-key")
        self.assertEqual(sanitized[0]["description"], "AWS Access Key")
        self.assertEqual(sanitized[0]["file"], "config.yml")
        self.assertEqual(sanitized[0]["line"], 10)
        self.assertEqual(sanitized[0]["commit"], "abcdef12")
        self.assertEqual(sanitized[0]["full_commit"], "abcdef1234567890")
        self.assertEqual(sanitized[0]["author"], "dev")
        self.assertEqual(sanitized[0]["date"], "2023-01-01")
        self.assertNotIn("Secret", sanitized[0])
        self.assertNotIn("Match", sanitized[0])

    def test_get_all_repositories(self):
        self.allowlist.list_repositories.return_value = ["allowed/repo", "allowed/repo-error"]
        mock_allowed_repo = MagicMock()
        mock_allowed_repo.default_branch = "main"

        mock_user = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.owner.login = "testowner"
        mock_user_repo.full_name = "testowner/repo1"
        mock_user_repo.default_branch = "master"

        mock_other_repo = MagicMock()
        mock_other_repo.owner.login = "otherowner" # Should be skipped

        mock_user.get_repos.return_value = [mock_user_repo, mock_other_repo]
        self.github_client.g.get_user.return_value = mock_user

        def mock_get_repo(name):
            if name == "allowed/repo":
                return mock_allowed_repo
            raise Exception("Not found")
        self.github_client.get_repo.side_effect = mock_get_repo

        repos = self.agent._get_all_repositories()

        self.assertEqual(len(repos), 2)
        repo_names = [r["name"] for r in repos]
        self.assertIn("allowed/repo", repo_names)
        self.assertIn("testowner/repo1", repo_names)

    def test_get_all_repositories_exception(self):
        self.allowlist.list_repositories.side_effect = Exception("API error")
        repos = self.agent._get_all_repositories()
        self.assertEqual(repos, [])

    def test_get_all_repositories_user_repos_exception(self):
        self.allowlist.list_repositories.return_value = ["allowed/repo"]
        mock_allowed_repo = MagicMock()
        mock_allowed_repo.default_branch = "main"

        def mock_get_repo(name):
            if name == "allowed/repo":
                return mock_allowed_repo
            raise Exception("Not found")
        self.github_client.get_repo.side_effect = mock_get_repo

        self.github_client.g.get_user.side_effect = Exception("User not found")
        repos = self.agent._get_all_repositories()
        self.assertEqual(len(repos), 1)

    @patch.object(SecurityScannerAgent, "_ensure_gitleaks_installed")
    def test_run_gitleaks_install_failed(self, mock_ensure):
        mock_ensure.return_value = False

        result = self.agent.run()
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Failed to install gitleaks. Cannot proceed with security scan.")
        self.telegram.send_message.assert_called_once()

    @patch.object(SecurityScannerAgent, "_send_notification")
    @patch.object(SecurityScannerAgent, "_get_all_repositories")
    @patch.object(SecurityScannerAgent, "_ensure_gitleaks_installed")
    def test_run_no_repositories(self, mock_ensure, mock_get_repos, mock_send_notif):
        mock_ensure.return_value = True
        mock_get_repos.return_value = []

        result = self.agent.run()
        self.assertEqual(result["total_repositories"], 0)
        mock_send_notif.assert_called_once()

    @patch.object(SecurityScannerAgent, "_send_notification")
    @patch.object(SecurityScannerAgent, "_scan_repository")
    @patch.object(SecurityScannerAgent, "_get_all_repositories")
    @patch.object(SecurityScannerAgent, "_ensure_gitleaks_installed")
    def test_run_with_findings_and_errors(self, mock_ensure, mock_get_repos, mock_scan_repo, mock_send_notif):
        mock_ensure.return_value = True
        mock_get_repos.return_value = [
            {"name": "repo1", "default_branch": "main"},
            {"name": "repo2", "default_branch": "master"},
            {"name": "repo3", "default_branch": "main"}
        ]

        def mock_scan(repo_name, default_branch):
            if repo_name == "repo1":
                return {"scanned": True, "findings": [{"rule_id": "r1"}], "error": None}
            elif repo_name == "repo2":
                return {"scanned": False, "findings": [], "error": "Scan failed"}
            else:
                raise Exception("Unexpected scan error")

        mock_scan_repo.side_effect = mock_scan

        result = self.agent.run()

        self.assertEqual(result["total_repositories"], 3)
        self.assertEqual(result["scanned"], 1)
        self.assertEqual(result["failed"], 2)
        self.assertEqual(result["total_findings"], 1)
        self.assertEqual(len(result["repositories_with_findings"]), 1)
        self.assertEqual(len(result["scan_errors"]), 2)

        mock_send_notif.assert_called_once_with(result)

    @patch.object(SecurityScannerAgent, "_get_commit_author")
    def test_send_notification(self, mock_get_author):
        mock_get_author.return_value = "testuser"

        results = {
            "scanned": 1,
            "total_repositories": 1,
            "failed": 1,
            "total_findings": 12, # Test truncation > 10
            "repositories_with_findings": [
                {
                    "repository": "test/repo",
                    "default_branch": "main",
                    "findings": [{"rule_id": f"rule-{i}", "file": f"f{i}.txt", "line": i, "commit": "123"} for i in range(12)]
                }
            ],
            "scan_errors": [
                {"repository": "test/error-repo", "error": "Something went wrong"}
            ]
        }

        self.agent._send_notification(results)
        self.assertTrue(self.telegram.send_message.called)

        # make sure at least one of the messages contains the header text
        sent_texts = [c[0][0] for c in self.telegram.send_message.call_args_list]
        self.assertTrue(any("Relatório do Security Scanner" in t for t in sent_texts))
        self.assertTrue(any("outros achados" in t for t in sent_texts))
        self.assertTrue(any("Erros de Scan" in t for t in sent_texts))

    @patch.object(SecurityScannerAgent, "_get_commit_author")
    def test_send_notification_multiple_messages(self, mock_get_author):
        mock_get_author.return_value = "testuser"

        results = {
            "scanned": 1,
            "total_repositories": 1,
            "failed": 0,
            "total_findings": 50,
            "repositories_with_findings": [
                {
                    "repository": f"test/repo-{i}",
                    "default_branch": "main",
                    "findings": [{"rule_id": "rule", "file": "f.txt", "line": 1, "commit": "123"} for _ in range(11)]
                } for i in range(5)
            ],
            "scan_errors": []
        }

        # force message to exceed 3800 chars
        long_name = "x" * 1000
        for i in range(len(results["repositories_with_findings"])):
            results["repositories_with_findings"][i]["repository"] = f"test/{long_name}-{i}"

        self.agent._send_notification(results)
        # header + at least one repo message = more than one call
        self.assertTrue(self.telegram.send_message.call_count > 1)
        # also verify that no message exceeds the length limit
        for c in self.telegram.send_message.call_args_list:
            msg_text = c[0][0]
            self.assertLessEqual(len(msg_text), 3800)

    def test_send_error_notification(self):
        self.agent._send_error_notification("A test error")
        self.telegram.send_message.assert_called_once()
        self.assertIn("A test error", self.telegram.send_message.call_args[0][0])

    @patch.object(SecurityScannerAgent, "_get_commit_author")
    def test_send_notification_truncates_long_lines(self, mock_get_author):
        mock_get_author.return_value = "user"
        # swap in a real notifier so that _truncate behaves predictably
        from src.notifications.telegram import TelegramNotifier
        real_telegram = TelegramNotifier(bot_token="bot", chat_id="chat")
        # keep escape consistent with earlier MagicMock helper
        real_telegram.escape = self.telegram.escape
        # replace agent's telegram and spy on send_message
        self.agent.telegram = real_telegram
        self.agent.telegram.send_message = MagicMock()

        # create one repo with a finding that has an enormous file path
        long_path = "a" * 5000
        results = {
            "scanned": 1,
            "total_repositories": 1,
            "failed": 0,
            "total_findings": 1,
            "repositories_with_findings": [
                {
                    "repository": "repo/long",
                    "default_branch": "main",
                    "findings": [
                        {"rule_id": "rule", "file": long_path, "line": 1, "commit": "123"}
                    ]
                }
            ],
            "scan_errors": []
        }
        self.agent._send_notification(results)
        # Should have at least two messages: header + repo details
        self.assertGreaterEqual(self.agent.telegram.send_message.call_count, 2)
        # the long line should have been truncated by TelegramNotifier._truncate
        calls = self.agent.telegram.send_message.call_args_list
        self.assertTrue(any("mensagem truncada" in c[0][0] for c in calls))

    def test_get_commit_author(self):
        # Empty sha
        self.assertEqual(self.agent._get_commit_author("repo", ""), "unknown")

        # Cache hit
        self.agent._commit_author_cache["repo:123"] = "cached_user"
        self.assertEqual(self.agent._get_commit_author("repo", "123"), "cached_user")

        # Cache miss, successful fetch
        mock_repo = MagicMock()
        mock_commit = MagicMock()
        mock_commit.author.login = "fetched_user"
        mock_repo.get_commit.return_value = mock_commit
        self.github_client.g.get_repo.return_value = mock_repo

        self.assertEqual(self.agent._get_commit_author("repo", "456"), "fetched_user")
        self.assertEqual(self.agent._commit_author_cache["repo:456"], "fetched_user")

        # Cache miss, missing author login
        mock_commit.author.login = None
        self.assertEqual(self.agent._get_commit_author("repo", "789"), "unknown")

        # Cache miss, exception
        self.github_client.g.get_repo.side_effect = Exception("API Error")
        self.assertEqual(self.agent._get_commit_author("repo", "error"), "unknown")

if __name__ == "__main__":
    unittest.main()
