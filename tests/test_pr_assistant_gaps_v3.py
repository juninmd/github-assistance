import subprocess
import unittest
from unittest.mock import MagicMock, mock_open, patch

from src.agents.pr_assistant.agent import PRAssistantAgent


class TestPRAssistantGapsV3(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.agent = PRAssistantAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            target_owner="juninmd"
        )

    def test_get_prs_to_process_specific_number(self):
        # Test specific_pr="123" (just number)
        issue = MagicMock()
        issue.number = 123
        issue.repository.full_name = "juninmd/repo"

        self.mock_github.search_prs.return_value = [issue]
        self.mock_github.get_pr_from_issue.return_value = MagicMock()

        result = self.agent._get_prs_to_process("123")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["number"], 123)
        self.assertEqual(result[0]["repository"], "juninmd/repo")

    def test_get_prs_to_process_specific_number_not_found(self):
        # Test specific_pr="123" but not found in search results
        self.mock_github.search_prs.return_value = [] # No issues found

        result = self.agent._get_prs_to_process("123")
        self.assertEqual(len(result), 0)

    def test_check_pipeline_status_no_commits(self):
        pr = MagicMock()
        pr.get_commits.return_value.totalCount = 0

        result = self.agent.check_pipeline_status(pr)
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "no_commits")

    def test_check_pipeline_status_exception(self):
        pr = MagicMock()
        pr.get_commits.side_effect = Exception("API Error")

        result = self.agent.check_pipeline_status(pr)
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "error")

    @patch("src.agents.pr_assistant.agent.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_resolve_conflicts_same_repo(self, mock_run, mock_temp):
        # Test conflict resolution on same repo (not fork)
        pr = MagicMock()
        pr.head.repo.id = 1
        pr.base.repo.id = 1 # Same ID
        pr.head.repo.clone_url = "url"
        pr.base.repo.clone_url = "url"

        mock_temp.return_value.__enter__.return_value = "/tmp"

        # Mock git commands success
        # We need to ensure subprocess.run doesn't fail

        # Mock merge failure (conflict)
        def side_effect(cmd, **kwargs):
            if "merge" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        # Mock diff output (no conflicts found? or mock check_output)
        with patch("subprocess.check_output", return_value=b""):
             result = self.agent.resolve_conflicts_autonomously(pr)
             # Should return True (commits empty fix if no files found? or fails?)
             # The code: if not file_path: continue. If loop finishes, commit.
             # So it commits "fix: resolve merge conflicts autonomously"
             self.assertTrue(result)

    def test_handle_pipeline_failure_already_commented(self):
        pr = MagicMock()
        comment = MagicMock()
        comment.body = "Pipeline failed with status:"
        self.mock_github.get_issue_comments.return_value = [comment]

        self.agent.handle_pipeline_failure(pr, "desc")
        # Should return early
        pr.create_issue_comment.assert_not_called()

    def test_run_specific_pr_fetches_obj(self):
        # Test that if _get_prs_to_process returns item without pr_obj, run fetches it
        # This covers the 'if not pr: pr = ...' line in run()

        # Setup _get_prs_to_process to return list without pr_obj
        # We can bypass _get_prs_to_process by mocking it, or use the path that produces it
        # Path: specific_pr="owner/repo#123"

        # Mock get_pr
        mock_pr = MagicMock()
        mock_pr.number = 123
        mock_pr.draft = False
        self.mock_github.get_pr.return_value = mock_pr

        with patch.object(self.agent, 'process_pr') as mock_process:
            mock_process.return_value = {"action": "merged", "pr": 123}

            self.agent.run(specific_pr="owner/repo#123")

            self.mock_github.get_pr.assert_called_with("owner/repo", 123)

    def test_get_pr_age_minutes_naive(self):
        # Test with naive datetime
        pr = MagicMock()
        from datetime import datetime
        pr.created_at = datetime(2023, 1, 1, 12, 0, 0) # Naive

        # Should not raise error and should convert to timezone aware
        age = self.agent.get_pr_age_minutes(pr)
        self.assertIsInstance(age, float)

    def test_handle_conflicts_success(self):
        pr = MagicMock()
        pr.user.login = "juninmd"
        with patch.object(self.agent, 'resolve_conflicts_autonomously', return_value=True):
            result = self.agent.handle_conflicts(pr)
            self.assertEqual(result["action"], "conflicts_resolved")

    def test_handle_conflicts_fail_fallback(self):
        pr = MagicMock()
        pr.user.login = "juninmd"
        with patch.object(self.agent, 'resolve_conflicts_autonomously', return_value=False):
            with patch.object(self.agent, 'notify_conflicts') as mock_notify:
                mock_notify.return_value = {"action": "notified"}
                result = self.agent.handle_conflicts(pr)
                self.assertEqual(result["action"], "notified")

    def test_handle_pipeline_failure_comments_exception(self):
        pr = MagicMock()
        self.mock_github.get_issue_comments.side_effect = Exception("API Error")

        # Should catch and continue to generate comment
        with patch.object(self.agent.ai_client, 'generate_pr_comment', return_value="Comment"):
             self.agent.handle_pipeline_failure(pr, "desc")
             pr.create_issue_comment.assert_called()

    @patch("src.agents.pr_assistant.agent.tempfile.TemporaryDirectory")
    @patch("subprocess.run")
    def test_resolve_conflicts_git_config_fail(self, mock_run, mock_temp):
        mock_temp.return_value.__enter__.return_value = "/tmp"
        pr = MagicMock()
        pr.base.repo.clone_url = "url"
        pr.head.repo.clone_url = "url"

        # clone succeeds
        # config fails
        def side_effect(cmd, **kwargs):
            if "config" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        result = self.agent.resolve_conflicts_autonomously(pr)
        self.assertFalse(result)

    def test_check_pipeline_status_neutral(self):
        pr = MagicMock()
        pr.get_commits.return_value.reversed = [MagicMock()]
        pr.get_commits.return_value.totalCount = 1

        pr.get_commits.return_value.reversed[0].get_combined_status.return_value.state = "neutral"
        pr.get_commits.return_value.reversed[0].get_check_runs.return_value = []

        result = self.agent.check_pipeline_status(pr)
        self.assertTrue(result["success"])

if __name__ == '__main__':
    unittest.main()
