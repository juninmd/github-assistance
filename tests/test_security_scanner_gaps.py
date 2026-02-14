import unittest
from unittest.mock import MagicMock, patch
from src.agents.security_scanner.agent import SecurityScannerAgent
import subprocess
import os

class TestSecurityScannerGaps(unittest.TestCase):
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

    def test_ensure_gitleaks_installed_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["cmd"], 10)):
             result = self.agent._ensure_gitleaks_installed()
             self.assertFalse(result)

    def test_scan_repository_timeout(self):
        with patch("tempfile.TemporaryDirectory") as mock_tmp:
            mock_tmp.return_value.__enter__.return_value = "/tmp"
            with patch("os.getenv", return_value="token"):
                with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["cmd"], 10)):
                     result = self.agent._scan_repository("repo")
                     self.assertEqual(result["error"], "Scan timeout exceeded")

    def test_run_scan_exception(self):
        """Test run() handles exception during scan."""
        with patch.object(self.agent, '_ensure_gitleaks_installed', return_value=True):
             with patch.object(self.agent, '_get_all_repositories') as mock_get_repos:
                  mock_get_repos.return_value = [{"name": "repo1", "default_branch": "main"}]
                  with patch.object(self.agent, '_scan_repository', side_effect=Exception("Scan Crash")):
                       results = self.agent.run()
                       self.assertEqual(results["failed"], 1)
                       self.assertIn("Scan Crash", results["scan_errors"][0]["error"])

    def test_run_scan_failed_false(self):
        """Test run() handles scan failure (scanned=False)."""
        with patch.object(self.agent, '_ensure_gitleaks_installed', return_value=True):
             with patch.object(self.agent, '_get_all_repositories') as mock_get_repos:
                  mock_get_repos.return_value = [{"name": "repo1", "default_branch": "main"}]
                  # scanned=False, error="Clone failed"
                  with patch.object(self.agent, '_scan_repository', return_value={"scanned": False, "error": "Clone failed", "findings": []}):
                       results = self.agent.run()
                       self.assertEqual(results["failed"], 1)
                       self.assertEqual(results["scan_errors"][0]["error"], "Clone failed")

    def test_get_all_repositories_exception(self):
        self.mock_github.g.get_user.side_effect = Exception("API Error")
        repos = self.agent._get_all_repositories()
        self.assertEqual(repos, [])

    def test_run_install_fail(self):
        with patch.object(self.agent, '_ensure_gitleaks_installed', return_value=False):
             result = self.agent.run()
             self.assertIn("Failed to install", result["error"])

    def test_run_no_repos(self):
        with patch.object(self.agent, '_ensure_gitleaks_installed', return_value=True):
             with patch.object(self.agent, '_get_all_repositories', return_value=[]):
                  result = self.agent.run()
                  self.assertEqual(result["total_repositories"], 0)

    def test_get_all_repositories_filter(self):
        mock_repo1 = MagicMock(); mock_repo1.full_name="juninmd/repo1"; mock_repo1.owner.login="juninmd"
        mock_repo2 = MagicMock(); mock_repo2.full_name="juninmd/fork"; mock_repo2.owner.login="other"

        self.mock_github.g.get_user.return_value.get_repos.return_value = [mock_repo1, mock_repo2]

        repos = self.agent._get_all_repositories()
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]["name"], "juninmd/repo1")

    def test_send_notification_truncation_errors(self):
        """Test truncation of scan errors in notification."""
        # Create many errors to force truncation
        errors = [{"repository": f"repo{i}", "error": "E" * 50} for i in range(100)]
        results = {
            "scanned": 100, "total_repositories": 100, "failed": 100,
            "total_findings": 0, "repositories_with_findings": [],
            "scan_errors": errors
        }

        self.agent._send_notification(results)

        msg = self.mock_github.send_telegram_msg.call_args[0][0]
        self.assertIn("Erros de Scan", msg)
        self.assertIn("e mais", msg)

    def test_send_notification_truncation_findings(self):
        """Test truncation of findings (repos) in notification."""
        repos = []
        for i in range(60):
             repos.append({
                 "repository": f"very_long_repo_name_{i}" * 5,
                 "default_branch": "main",
                 "findings": [
                     {"rule_id": "rule", "file": "file", "line": 1, "commit": "abc", "author": "me"}
                 ]
             })

        results = {
            "scanned": 60, "total_repositories": 60, "failed": 0,
            "total_findings": 60, "repositories_with_findings": repos,
            "scan_errors": []
        }

        self.agent._send_notification(results)
        msg = self.mock_github.send_telegram_msg.call_args[0][0]
        self.assertIn("e mais", msg)

if __name__ == '__main__':
    unittest.main()
