import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
import subprocess
import json
from src.agents.security_scanner.agent import SecurityScannerAgent

class TestSecurityScannerCoverage(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()

        # Patch BaseAgent.__init__ to avoid config loading issues if needed
        # But BaseAgent logic is simple, so we might not need it.
        # We'll just patch dependencies.
        self.agent = SecurityScannerAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            target_owner="juninmd"
        )

    @patch("subprocess.run")
    def test_ensure_gitleaks_installed_already(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "8.18.1"

        result = self.agent._ensure_gitleaks_installed()
        self.assertTrue(result)
        mock_run.assert_called_with(["gitleaks", "version"], capture_output=True, text=True, timeout=10)

    @patch("subprocess.run")
    def test_ensure_gitleaks_install_success(self, mock_run):
        # First call (version check) fails (file not found)
        # Second call (install) succeeds
        mock_run.side_effect = [
            FileNotFoundError(), # version check
            MagicMock(returncode=0) # install script
        ]

        result = self.agent._ensure_gitleaks_installed()
        self.assertTrue(result)

    @patch("subprocess.run")
    def test_ensure_gitleaks_install_failure(self, mock_run):
        # Version check fails, install fails
        mock_run.side_effect = [
            FileNotFoundError(),
            MagicMock(returncode=1)
        ]

        result = self.agent._ensure_gitleaks_installed()
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_ensure_gitleaks_install_exception(self, mock_run):
        # First call fails (triggering install attempt), second call raises generic exception
        mock_run.side_effect = [
            FileNotFoundError(),
            Exception("Boom")
        ]
        result = self.agent._ensure_gitleaks_installed()
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_scan_repository_no_token(self, mock_run):
        with patch.dict(os.environ, {}, clear=True):
            result = self.agent._scan_repository("user/repo")
            self.assertEqual(result["error"], "GITHUB_TOKEN not available")

    @patch("subprocess.run")
    def test_scan_repository_clone_fail(self, mock_run):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True):
            mock_run.return_value.returncode = 128 # git error
            result = self.agent._scan_repository("user/repo")
            self.assertIn("Clone failed", result["error"])

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_scan_repository_scan_fail_code(self, mock_exists, mock_run):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True):
            # Clone success
            # Scan returns 2 (error)
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=2)
            ]
            result = self.agent._scan_repository("user/repo")
            self.assertIn("Gitleaks scan failed", result["error"])

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data='[{"RuleID": "aws-key", "File": "/tmp/repo/file.py", "StartLine": 1}]')
    def test_scan_repository_success_with_findings(self, mock_file, mock_exists, mock_run):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True):
            mock_run.side_effect = [
                MagicMock(returncode=0), # Clone
                MagicMock(returncode=1)  # Scan (1 means leaks found)
            ]
            mock_exists.return_value = True

            result = self.agent._scan_repository("user/repo")

            self.assertTrue(result["scanned"])
            self.assertEqual(len(result["findings"]), 1)
            self.assertEqual(result["findings"][0]["rule_id"], "aws-key")

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data='invalid json')
    def test_scan_repository_json_error(self, mock_file, mock_exists, mock_run):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True):
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=1)
            ]
            mock_exists.return_value = True

            result = self.agent._scan_repository("user/repo")
            self.assertIn("Failed to parse", result["error"])

    @patch("subprocess.run")
    def test_scan_repository_timeout(self, mock_run):
         with patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True):
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)
            result = self.agent._scan_repository("user/repo")
            self.assertEqual(result["error"], "Scan timeout exceeded")

    @patch("src.agents.security_scanner.agent.SecurityScannerAgent._get_all_repositories")
    @patch("src.agents.security_scanner.agent.SecurityScannerAgent._ensure_gitleaks_installed")
    @patch("src.agents.security_scanner.agent.SecurityScannerAgent._scan_repository")
    def test_run_full_flow(self, mock_scan, mock_ensure, mock_get_repos):
        mock_ensure.return_value = True
        mock_get_repos.return_value = [{"name": "repo1", "default_branch": "main"}]
        mock_scan.return_value = {"scanned": True, "findings": [{"rule_id": "test", "file": "f", "line": 1}]}

        self.agent.run()

        self.mock_github.send_telegram_msg.assert_called()

    @patch("src.agents.security_scanner.agent.SecurityScannerAgent._ensure_gitleaks_installed")
    def test_run_install_fail(self, mock_ensure):
        mock_ensure.return_value = False
        result = self.agent.run()
        self.assertIn("error", result)

    @patch("src.agents.security_scanner.agent.SecurityScannerAgent._ensure_gitleaks_installed")
    @patch("src.agents.security_scanner.agent.SecurityScannerAgent._get_all_repositories")
    def test_run_no_repos(self, mock_get, mock_ensure):
        mock_ensure.return_value = True
        mock_get.return_value = []
        result = self.agent.run()
        self.assertEqual(result["total_repositories"], 0)

    def test_escape_telegram(self):
        text = "Hello_world!"
        escaped = self.agent._escape_telegram(text)
        self.assertEqual(escaped, "Hello\\_world\\!")

    def test_get_all_repositories_filtering(self):
        user = MagicMock()
        repo_owned = MagicMock(); repo_owned.owner.login = "juninmd"; repo_owned.full_name = "juninmd/r1"; repo_owned.default_branch = "main"
        repo_fork = MagicMock(); repo_fork.owner.login = "other"; repo_fork.full_name = "other/r2"

        user.get_repos.return_value = [repo_owned, repo_fork]
        self.mock_github.g.get_user.return_value = user

        repos = self.agent._get_all_repositories()
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]["name"], "juninmd/r1")

    def test_get_all_repositories_exception(self):
        self.mock_github.g.get_user.side_effect = Exception("API Error")
        repos = self.agent._get_all_repositories()
        self.assertEqual(repos, [])

    def test_notification_limit_and_format(self):
        findings = []
        for i in range(10):
            findings.append({
                "rule_id": f"rule{i}",
                "file": f"file{i}.py",
                "line": i,
                "author": f"Author{i}",
                "commit": "abc1234",
                "description": "desc"
            })

        results = {
            "scanned": 1,
            "total_repositories": 1,
            "failed": 0,
            "total_findings": 10,
            "all_repositories": [{"name": "juninmd/repo1", "default_branch": "main"}],
            "repositories_with_findings": [{
                "repository": "juninmd/repo1",
                "default_branch": "main",
                "findings": findings
            }],
            "scan_errors": []
        }

        self.agent._send_notification(results)

        args = self.mock_github.send_telegram_msg.call_args
        if args:
            message = args[0][0]
            # Verify limit is 5
            count = message.count("rule")
            self.assertEqual(count, 5, f"Expected 5 findings, got {count}")

            # Verify format contains author and link
            self.assertIn("rule0", message)
            self.assertIn("@Author0", message)
            self.assertIn("https://github.com/juninmd/repo1/blob/main/file0.py#L0", message)

        else:
            self.fail("send_telegram_msg was not called")
