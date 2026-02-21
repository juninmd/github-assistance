import unittest
from unittest.mock import MagicMock, patch, mock_open
import subprocess
import os
import json
from src.agents.security_scanner.agent import SecurityScannerAgent

class TestSecurityScannerGapsV2(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.agent = SecurityScannerAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            target_owner="juninmd"
        )

    @patch("subprocess.run")
    def test_ensure_gitleaks_timeout_check(self, mock_run):
        # First check times out, installation succeeds
        mock_run.side_effect = [
            subprocess.TimeoutExpired(cmd="gitleaks version", timeout=10),
            MagicMock(returncode=0) # Install success
        ]

        result = self.agent._ensure_gitleaks_installed()
        self.assertTrue(result)

    @patch("subprocess.run")
    def test_ensure_gitleaks_install_fail(self, mock_run):
        # First check fails (FileNotFound), installation fails
        mock_run.side_effect = [
            FileNotFoundError(),
            MagicMock(returncode=1) # Install failure
        ]

        result = self.agent._ensure_gitleaks_installed()
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_ensure_gitleaks_install_exception(self, mock_run):
        # First check fails, installation raises exception
        mock_run.side_effect = [
            FileNotFoundError(),
            Exception("Install Error")
        ]

        result = self.agent._ensure_gitleaks_installed()
        self.assertFalse(result)

    @patch("src.agents.security_scanner.agent.tempfile.TemporaryDirectory")
    def test_scan_repository_no_token(self, mock_temp):
        with patch.dict(os.environ, {}, clear=True):
            result = self.agent._scan_repository("owner/repo")
            self.assertEqual(result["error"], "GITHUB_TOKEN not available")

    @patch("src.agents.security_scanner.agent.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_scan_repository_clone_fail(self, mock_run, mock_temp):
        mock_temp.return_value.__enter__.return_value = "/tmp"
        with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}):
            mock_run.return_value = MagicMock(returncode=128) # Clone fail

            result = self.agent._scan_repository("owner/repo")
            self.assertIn("Clone failed", result["error"])

    @patch("src.agents.security_scanner.agent.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_scan_repository_gitleaks_fail_code(self, mock_run, mock_temp):
        mock_temp.return_value.__enter__.return_value = "/tmp"
        with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}):
            # Clone success, Gitleaks fail code (not 0 or 1)
            mock_run.side_effect = [
                MagicMock(returncode=0), # Clone
                MagicMock(returncode=2)  # Gitleaks error
            ]

            result = self.agent._scan_repository("owner/repo")
            self.assertIn("Gitleaks scan failed", result["error"])

    @patch("src.agents.security_scanner.agent.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_scan_repository_json_error(self, mock_run, mock_temp):
        mock_temp.return_value.__enter__.return_value = "/tmp"
        with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}):
            mock_run.side_effect = [
                MagicMock(returncode=0), # Clone
                MagicMock(returncode=1)  # Gitleaks findings found
            ]

            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", mock_open(read_data="invalid-json")):
                    result = self.agent._scan_repository("owner/repo")
                    self.assertIn("Failed to parse", result["error"])

    @patch("src.agents.security_scanner.agent.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_scan_repository_timeout(self, mock_run, mock_temp):
        mock_temp.return_value.__enter__.return_value = "/tmp"
        with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}):
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git clone", timeout=300)

            result = self.agent._scan_repository("owner/repo")
            self.assertEqual(result["error"], "Scan timeout exceeded")

    def test_send_notification_pagination(self):
        # Create a result with VERY long lines to trigger pagination
        results = {
            "scanned": 100,
            "total_repositories": 100,
            "failed": 50,
            "total_findings": 1000,
            "repositories_with_findings": [],
            "scan_errors": [],
            "all_repositories": []
        }

        # Add many findings
        findings = []
        for i in range(10):
            findings.append({
                "rule_id": f"rule-{i}",
                "file": f"path/to/very/long/file/name/that/takes/up/space/{i}.js",
                "line": i,
                "author": "dev"
            })

        # Add MANY repos to fill the message
        for i in range(100):
            results["repositories_with_findings"].append({
                "repository": f"owner/repo-{i}",
                "findings": findings
            })

        # Also add many scan errors
        for i in range(50):
            results["scan_errors"].append({
                "repository": f"owner/repo-{i}",
                "error": "Some error occurred during scan" * 5
            })

        self.agent._send_notification(results)
        # Verify send_telegram_msg was called multiple times
        self.assertGreater(self.mock_github.send_telegram_msg.call_count, 1)

    def test_get_commit_author_cache(self):
        self.agent._commit_author_cache = {"repo:sha": "cached_user"}
        author = self.agent._get_commit_author("repo", "sha")
        self.assertEqual(author, "cached_user")
        self.mock_github.g.get_repo.assert_not_called()

    def test_get_commit_author_api_error(self):
        self.mock_github.g.get_repo.side_effect = Exception("API Error")
        author = self.agent._get_commit_author("repo", "sha")
        self.assertEqual(author, "unknown")

    def test_get_all_repositories_exception(self):
        self.mock_github.g.get_user.side_effect = Exception("API Error")
        repos = self.agent._get_all_repositories()
        self.assertEqual(repos, [])

    @patch("subprocess.run")
    def test_ensure_gitleaks_check_fails_code(self, mock_run):
        # First check returns non-zero code, falls through to install
        mock_run.side_effect = [
            MagicMock(returncode=1), # Version check fails
            MagicMock(returncode=0)  # Install success
        ]
        result = self.agent._ensure_gitleaks_installed()
        self.assertTrue(result)

    @patch("src.agents.security_scanner.agent.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_scan_repository_relpath(self, mock_run, mock_temp):
        mock_temp.return_value.__enter__.return_value = "/tmp"
        clone_dir = os.path.join("/tmp", "repo")

        with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}):
            mock_run.return_value = MagicMock(returncode=0)

            with patch("os.path.exists", return_value=True):
                # Findings with absolute path
                findings = [{"File": os.path.join(clone_dir, "secret.js"), "StartLine": 1}]
                with patch("builtins.open", mock_open(read_data=json.dumps(findings))):
                    result = self.agent._scan_repository("owner/repo")
                    self.assertEqual(result["findings"][0]["file"], "secret.js")

    def test_get_all_repositories_filter_owner(self):
        user = MagicMock()
        repo_owned = MagicMock(full_name="juninmd/owned", default_branch="main")
        repo_owned.owner.login = "juninmd"

        repo_fork = MagicMock(full_name="juninmd/fork", default_branch="main")
        repo_fork.owner.login = "other"

        user.get_repos.return_value = [repo_owned, repo_fork]
        self.mock_github.g.get_user.return_value = user

        repos = self.agent._get_all_repositories()
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]["name"], "juninmd/owned")

if __name__ == '__main__':
    unittest.main()
