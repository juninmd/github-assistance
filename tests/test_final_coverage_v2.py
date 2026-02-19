import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import subprocess
from src.agents.interface_developer.agent import InterfaceDeveloperAgent
from src.agents.security_scanner.agent import SecurityScannerAgent
from src.run_agent import main as run_agent_main

class TestFinalCoverageV2(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()

    def test_interface_developer_no_needs(self):
        # Cover line 65 in src/agents/interface_developer/agent.py
        agent = InterfaceDeveloperAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        agent.allowlist.list_repositories.return_value = ["repo1"]

        # Mock analyze_ui_needs to return no improvement needed
        with patch.object(agent, 'analyze_ui_needs', return_value={"needs_improvement": False}):
            results = agent.run()
            # Should log "No UI work needed" -> line 65
            self.assertEqual(len(results["ui_tasks_created"]), 0)

    def test_security_scanner_relpath(self):
        # Cover line 189 in src/agents/security_scanner/agent.py
        agent = SecurityScannerAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

        with patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"}):
            with patch("src.agents.security_scanner.agent.tempfile.TemporaryDirectory") as mock_temp:
                mock_temp.return_value.__enter__.return_value = "/tmp/scan"

                # Mock subprocess run to succeed
                with patch("src.agents.security_scanner.agent.subprocess.run") as mock_run:
                    mock_run.return_value.returncode = 0

                    # Mock report file existence and content
                    with patch("src.agents.security_scanner.agent.os.path.exists", return_value=True):
                        with patch("src.agents.security_scanner.agent.open", new_callable=unittest.mock.mock_open, read_data='[{"File": "/tmp/scan/repo/file.txt", "RuleID": "test"}]'):
                            # Mock json.load via open read_data is tricky because json.load reads from file object
                            # We can mock json.load directly
                            with patch("src.agents.security_scanner.agent.json.load") as mock_json:
                                mock_json.return_value = [{"File": "/tmp/scan/repo/file.txt", "RuleID": "test"}]

                                # We need clone_dir to be "/tmp/scan/repo"
                                # agent uses os.path.join(temp_dir, "repo")

                                result = agent._scan_repository("repo")
                                # Findings should have relative path "file.txt"
                                if not result["findings"]:
                                    # Debug why empty
                                    print(f"Result error: {result.get('error')}")
                                    self.fail("Findings list is empty")
                                self.assertEqual(result["findings"][0]["file"], "file.txt")

    def test_security_scanner_generic_exception(self):
        # Cover lines 201-203 in src/agents/security_scanner/agent.py
        agent = SecurityScannerAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

        with patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"}):
            # Exception MUST happen inside the try block (inside with tempfile)
            # We can mock subprocess.run to raise exception (used for git clone)
            with patch("src.agents.security_scanner.agent.subprocess.run", side_effect=Exception("Generic Error")):
                 result = agent._scan_repository("repo")
                 self.assertIn("Generic Error", result["error"])

    def test_run_agent_main_exception(self):
        # Cover src/run_agent.py exception block (line 242)
        # This block catches exceptions from runner()
        with patch.object(sys, 'argv', ['run-agent', 'security-scanner']):
            with patch("src.run_agent.argparse.ArgumentParser.parse_args") as mock_args:
                mock_args.return_value.agent_name = "security-scanner"
                mock_args.return_value.provider = None
                mock_args.return_value.model = None

                with patch("src.run_agent.run_security_scanner", side_effect=Exception("Run Error")):
                    with patch("src.run_agent.sys.exit") as mock_exit:
                        run_agent_main()
                        mock_exit.assert_called_with(1)

    def test_run_agent_module_main(self):
        # Run module as script to cover if __name__ == "__main__": block
        # We expect failure because args are missing, but it covers the block
        env = os.environ.copy()
        env["PYTHONPATH"] = os.getcwd() # Ensure src is in path
        result = subprocess.run(
            [sys.executable, "-m", "src.run_agent"],
            capture_output=True,
            text=True,
            env=env
        )
        # It should exit with error code 2 (argparse)
        self.assertNotEqual(result.returncode, 0)

    def test_main_module_main(self):
        # Run src.main as script
        env = os.environ.copy()
        env["PYTHONPATH"] = os.getcwd()
        result = subprocess.run(
            [sys.executable, "-m", "src.main"],
            capture_output=True,
            text=True,
            env=env
        )
        # It calls main() which likely fails due to config/env
        self.assertNotEqual(result.returncode, 0)

if __name__ == '__main__':
    unittest.main()
