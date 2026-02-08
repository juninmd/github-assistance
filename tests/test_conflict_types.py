import unittest
import subprocess
from unittest.mock import MagicMock, patch
from src.agents.pr_assistant.agent import PRAssistantAgent

class TestConflictTypes(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True
        self.agent = PRAssistantAgent(self.mock_github, self.mock_jules, self.mock_allowlist)

    @patch("src.agents.pr_assistant.agent.subprocess")
    @patch("src.agents.pr_assistant.agent.os")
    @patch("builtins.open")
    def test_handle_conflicts_AA(self, mock_open, mock_os, mock_subprocess):
        # Fix: Assign real Exception class to the mock
        mock_subprocess.CalledProcessError = subprocess.CalledProcessError

        # Simulate a PR with "Both Added" conflict
        pr = MagicMock()
        pr.number = 10
        pr.mergeable = False
        pr.head.repo.full_name = "fork/repo"
        pr.base.repo.full_name = "base/repo"

        # Mock git diff output to show just filename
        mock_subprocess.check_output.return_value = b"new_file.txt\n"

        # Mock subprocess.run to raise CalledProcessError for the merge command
        def side_effect(command, **kwargs):
            if command[0] == "git" and command[1] == "merge":
                raise subprocess.CalledProcessError(1, command)
            return MagicMock()

        mock_subprocess.run.side_effect = side_effect
        mock_os.path.exists.return_value = False

        # Mock reading the file
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        mock_file.read.return_value = "<<<<<<<\n=======\n>>>>>>>"

        self.mock_ai.resolve_conflict.return_value = "resolved"

        self.agent.handle_conflicts(pr)

        # Verify git diff was called
        found_diff = False
        for call in mock_subprocess.check_output.call_args_list:
            args = call[0][0]
            if args[0] == "git" and args[1] == "diff" and "--diff-filter=U" in args:
                found_diff = True
                break
        self.assertTrue(found_diff, "Should have called git diff --diff-filter=U")

        found_add = False
        for call in mock_subprocess.run.call_args_list:
            args = call[0][0]
            if args[0] == "git" and args[1] == "add" and args[2] == "new_file.txt":
                found_add = True
                break

        self.assertTrue(found_add, "Should have added conflict file")

if __name__ == '__main__':
    unittest.main()
