import unittest
from unittest.mock import MagicMock, patch, mock_open
from src.agents.pr_assistant.agent import PRAssistantAgent

class TestCoverageGapFill(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True

        with patch("src.agents.pr_assistant.agent.get_ai_client"):
            self.agent = PRAssistantAgent(
                self.mock_jules,
                self.mock_github,
                self.mock_allowlist,
                target_owner="juninmd"
            )

    def test_escape_telegram_empty(self):
        """Test _escape_telegram with empty input."""
        self.assertEqual(self.agent._escape_telegram(""), "")
        self.assertEqual(self.agent._escape_telegram(None), None)

    def test_process_pr_mergeable_none(self):
        """Test process_pr when mergeable is None."""
        pr = MagicMock()
        pr.user.login = "juninmd"
        pr.number = 1
        pr.mergeable = None

        # Bypass age check
        with patch.object(self.agent, 'is_pr_too_young', return_value=False):
             # Bypass google bot suggestions
             self.mock_github.accept_review_suggestions.return_value = (True, "", 0)

             result = self.agent.process_pr(pr)

             self.assertEqual(result["action"], "skipped")
             self.assertEqual(result["reason"], "mergeability_unknown")

    def test_process_pr_status_unknown_error(self):
        """Test process_pr when pipeline status returns unknown error."""
        pr = MagicMock()
        pr.user.login = "juninmd"
        pr.number = 1
        pr.mergeable = True

        with patch.object(self.agent, 'is_pr_too_young', return_value=False):
            self.mock_github.accept_review_suggestions.return_value = (True, "", 0)

            with patch.object(self.agent, 'check_pipeline_status') as mock_status:
                mock_status.return_value = {"success": False, "reason": "unknown", "details": "wtf"}

                result = self.agent.process_pr(pr)

                self.assertEqual(result["action"], "skipped")
                self.assertEqual(result["reason"], "status_error")

    def test_process_pr_merge_failed(self):
        """Test process_pr when merge fails."""
        pr = MagicMock()
        pr.user.login = "juninmd"
        pr.number = 1
        pr.mergeable = True

        with patch.object(self.agent, 'is_pr_too_young', return_value=False):
            self.mock_github.accept_review_suggestions.return_value = (True, "", 0)

            with patch.object(self.agent, 'check_pipeline_status', return_value={"success": True}):
                self.mock_github.merge_pr.return_value = (False, "Merge conflict or protection")

                result = self.agent.process_pr(pr)

                self.assertEqual(result["action"], "merge_failed")
                self.assertEqual(result["error"], "Merge conflict or protection")

    def test_resolve_conflicts_autonomously_clean_merge(self):
        """Test autonomous resolution where merge succeeds without conflicts."""
        pr = MagicMock()
        pr.base.repo.clone_url = "https://github.com/base/repo"
        pr.head.repo.clone_url = "https://github.com/head/repo"
        pr.head.repo.id = 1
        pr.base.repo.id = 2 # Different repo (fork)

        with patch("src.agents.pr_assistant.agent.tempfile.TemporaryDirectory") as mock_tmp:
            mock_tmp.return_value.__enter__.return_value = "/tmp/repo"
            with patch("subprocess.run") as mock_run:
                # Mock git merge success
                # git clone, config, config, remote add, checkout, fetch, merge (success), push
                mock_run.return_value.returncode = 0

                success = self.agent.resolve_conflicts_autonomously(pr)

                self.assertTrue(success)
                # Verify git push called
                push_call = [c for c in mock_run.call_args_list if "push" in c[0][0]]
                self.assertTrue(push_call)

    def test_notify_conflicts_create_comment_failure(self):
        """Test notify_conflicts when create_issue_comment fails."""
        pr = MagicMock()
        self.mock_github.get_issue_comments.return_value = []
        pr.create_issue_comment.side_effect = Exception("API Error")

        result = self.agent.notify_conflicts(pr)

        # Should still return action
        self.assertEqual(result["action"], "conflicts_detected")

    def test_handle_pipeline_failure_get_comments_failure(self):
        """Test handle_pipeline_failure when get_issue_comments fails."""
        pr = MagicMock()
        self.mock_github.get_issue_comments.side_effect = Exception("API Error")
        self.agent.ai_client.generate_pr_comment.return_value = "AI Comment"

        self.agent.handle_pipeline_failure(pr, "details")

        # Should proceed to create comment
        pr.create_issue_comment.assert_called_with("AI Comment")

if __name__ == '__main__':
    unittest.main()
