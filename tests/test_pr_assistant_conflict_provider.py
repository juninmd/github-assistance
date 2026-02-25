import unittest
from unittest.mock import MagicMock, patch, mock_open
import subprocess
import os
from src.agents.pr_assistant.agent import PRAssistantAgent

class TestPRAssistantConflictProvider(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()

        # Patch get_ai_client in __init__ (though agent imports it directly)
        # We need to patch where it's imported in agent.py
        with patch("src.agents.pr_assistant.agent.get_ai_client") as mock_get_ai:
            self.mock_ai_client = MagicMock()
            mock_get_ai.return_value = self.mock_ai_client

            # Initialize with custom provider to verify it's used
            self.agent = PRAssistantAgent(
                self.mock_jules,
                self.mock_github,
                self.mock_allowlist,
                target_owner="juninmd",
                ai_provider="custom_provider",
                ai_model="custom_model"
            )

    @patch("src.agents.pr_assistant.agent.tempfile.TemporaryDirectory")
    @patch("src.agents.pr_assistant.agent.subprocess.run")
    @patch("src.agents.pr_assistant.agent.subprocess.check_output")
    @patch("builtins.open", new_callable=mock_open)
    def test_resolve_conflicts_uses_configured_client(self, mock_file, mock_check_output, mock_run, mock_temp):
        # Setup mocks
        mock_temp.return_value.__enter__.return_value = "/tmp/repo"

        # PR Object setup
        pr = MagicMock()
        pr.number = 1
        pr.base.repo.clone_url = "https://github.com/base/repo"
        pr.head.repo.clone_url = "https://github.com/head/repo"
        pr.head.repo.id = 1
        pr.base.repo.id = 2 # Different ID -> fork
        pr.head.ref = "feature-branch"
        pr.base.ref = "main"

        # Mock subprocess behavior
        # We need check_output to return conflicted files for "git diff"
        # We need run to fail for "git merge"
        # We need run to succeed for others

        def run_side_effect(cmd, **kwargs):
            cmd_list = cmd if isinstance(cmd, list) else cmd.split()
            # Check if it's the merge command
            if "merge" in cmd_list:
                # Raise error to trigger conflict resolution path
                raise subprocess.CalledProcessError(1, cmd)
            return MagicMock(returncode=0)

        mock_run.side_effect = run_side_effect

        # Mock git diff returning one file
        mock_check_output.return_value = b"conflicted_file.txt\n"

        # Mock file content with conflict markers
        file_content = (
            "header\n"
            "<<<<<<< SEARCH\n"
            "code from base\n"
            "=======\n"
            "code from head\n"
            ">>>>>>> REPLACE\n"
            "footer"
        )
        mock_file.return_value.read.return_value = file_content

        # Mock AI resolution result
        self.mock_ai_client.resolve_conflict.return_value = "resolved code\n"

        # Execute
        result = self.agent.resolve_conflicts_autonomously(pr)

        # Verify result is True (success)
        self.assertTrue(result)

        # Verify AI client called (This is the key assertion)
        self.mock_ai_client.resolve_conflict.assert_called()

        # Check call arguments
        call_args = self.mock_ai_client.resolve_conflict.call_args
        self.assertIsNotNone(call_args)
        # conflict_block is the second argument to resolve_conflict(file_content, conflict_block)
        block_arg = call_args[0][1]

        self.assertIn("<<<<<<< SEARCH", block_arg)
        self.assertIn("=======", block_arg)
        self.assertIn(">>>>>>> REPLACE", block_arg)

        # Verify git push happened (meaning resolution succeeded)
        # We look for "push" in any call to run
        push_called = False
        for call in mock_run.call_args_list:
            args = call[0][0] # The command list
            if "push" in args and "origin" in args:
                push_called = True
                break
        self.assertTrue(push_called, "git push should have been called")

if __name__ == '__main__':
    unittest.main()
