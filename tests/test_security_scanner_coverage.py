import unittest
from unittest.mock import MagicMock, patch, mock_open
import subprocess
import os
from src.agents.security_scanner.agent import SecurityScannerAgent

class TestSecurityScannerCoverage(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        # Patch log to avoid clutter output
        self.patcher = patch("src.agents.base_agent.BaseAgent.log")
        self.mock_log = self.patcher.start()

        self.agent = SecurityScannerAgent(self.mock_jules, self.mock_github, self.mock_allowlist, target_owner="juninmd")

    def tearDown(self):
        self.patcher.stop()

    @patch("subprocess.run")
    def test_ensure_gitleaks_installed_error(self, mock_run):
        # First call fails (FileNotFound), install raises Exception
        mock_run.side_effect = [FileNotFoundError(), Exception("Error")]
        self.assertFalse(self.agent._ensure_gitleaks_installed())

    @patch("subprocess.run")
    def test_ensure_gitleaks_installed_install_fail(self, mock_run):
        # First check fails (not found)
        # Second check (install) fails
        mock_run.side_effect = [FileNotFoundError(), MagicMock(returncode=1)]
        self.assertFalse(self.agent._ensure_gitleaks_installed())

    @patch("src.agents.security_scanner.agent.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_scan_repository_gitleaks_error(self, mock_run, mock_temp):
        mock_temp.return_value.__enter__.return_value = "/tmp"

        # Clone success, gitleaks fail (exit code 2)
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=2)
        ]

        with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}):
            result = self.agent._scan_repository("repo")
            self.assertIn("Gitleaks scan failed", result["error"])

    @patch("src.agents.security_scanner.agent.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_scan_repository_json_error(self, mock_run, mock_temp):
        mock_temp.return_value.__enter__.return_value = "/tmp"

        # Clone success, gitleaks success (exit code 1 - found leaks)
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=1)
        ]

        with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", mock_open(read_data="{invalid_json")):
                    result = self.agent._scan_repository("repo")
                    self.assertIn("Failed to parse", result["error"])

    @patch("src.agents.security_scanner.agent.tempfile.TemporaryDirectory")
    def test_scan_repository_no_token(self, mock_temp):
        with patch.dict(os.environ, {}, clear=True):
            result = self.agent._scan_repository("repo")
            self.assertEqual(result["error"], "GITHUB_TOKEN not available")

    def test_get_all_repositories_error(self):
        self.mock_github.g.get_user.side_effect = Exception("Error")
        repos = self.agent._get_all_repositories()
        self.assertEqual(repos, [])

    @patch.object(SecurityScannerAgent, "_ensure_gitleaks_installed", return_value=False)
    def test_run_install_fail(self, mock_install):
        result = self.agent.run()
        self.assertIn("Failed to install gitleaks", result["error"])

    @patch.object(SecurityScannerAgent, "_ensure_gitleaks_installed", return_value=True)
    @patch.object(SecurityScannerAgent, "_get_all_repositories", return_value=[])
    def test_run_no_repos(self, mock_get_repos, mock_install):
        result = self.agent.run()
        self.assertEqual(result["total_repositories"], 0)

    @patch.object(SecurityScannerAgent, "_ensure_gitleaks_installed", return_value=True)
    @patch.object(SecurityScannerAgent, "_get_all_repositories")
    @patch.object(SecurityScannerAgent, "_scan_repository")
    def test_run_scan_exception(self, mock_scan, mock_get_repos, mock_install):
        mock_get_repos.return_value = [{"name": "repo1", "default_branch": "main"}]
        mock_scan.side_effect = Exception("Error")

        result = self.agent.run()
        self.assertEqual(result["failed"], 1)
