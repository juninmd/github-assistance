import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from src.agents.pr_assistant.agent import PRAssistantAgent


class TestPRAssistantPipelineDetails(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        with patch("src.agents.pr_assistant.agent.get_ai_client"):
            self.agent = PRAssistantAgent(
                self.mock_jules,
                self.mock_github,
                self.mock_allowlist,
                target_owner="owner"
            )

    def test_check_pipeline_status_billing_error(self):
        # Mock PR and commits
        mock_pr = MagicMock()
        mock_commit = MagicMock()
        mock_pr.get_commits.return_value = MagicMock(totalCount=1, reversed=[mock_commit])

        # Mock legacy status with billing error
        mock_status = MagicMock()
        mock_status.state = "failure"
        mock_status.context = "billing-check"
        mock_status.description = "account payments failed"

        mock_combined = MagicMock()
        mock_combined.state = "failure"
        mock_combined.total_count = 1
        mock_combined.statuses = [mock_status]
        mock_commit.get_combined_status.return_value = mock_combined

        result = self.agent.check_pipeline_status(mock_pr)
        self.assertTrue(result["success"])
        self.assertEqual(result["reason"], "failure")
        self.assertIn("billing/limit issues", result["details"])

    def test_check_pipeline_status_legacy_pending(self):
        mock_pr = MagicMock()
        mock_commit = MagicMock()
        mock_pr.get_commits.return_value = MagicMock(totalCount=1, reversed=[mock_commit])

        mock_combined = MagicMock()
        mock_combined.state = "pending"
        mock_combined.total_count = 1
        mock_combined.statuses = []
        mock_commit.get_combined_status.return_value = mock_combined

        result = self.agent.check_pipeline_status(mock_pr)
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "pending")
        self.assertIn("Legacy status is pending", result["details"])

    def test_check_pipeline_status_legacy_other_state(self):
        mock_pr = MagicMock()
        mock_commit = MagicMock()
        mock_pr.get_commits.return_value = MagicMock(totalCount=1, reversed=[mock_commit])

        mock_combined = MagicMock()
        mock_combined.state = "cancelled" # Not success, neutral, failure, error, pending
        mock_combined.total_count = 1
        mock_combined.statuses = []
        mock_commit.get_combined_status.return_value = mock_combined

        result = self.agent.check_pipeline_status(mock_pr)
        self.assertFalse(result["success"])
        self.assertIn("Legacy status is cancelled", result["details"])

    def test_check_pipeline_status_check_runs_failure_details(self):
        mock_pr = MagicMock()
        mock_commit = MagicMock()
        mock_pr.get_commits.return_value = MagicMock(totalCount=1, reversed=[mock_commit])

        # Legacy status success (to bypass it)
        mock_combined = MagicMock()
        mock_combined.state = "success"
        mock_commit.get_combined_status.return_value = mock_combined

        # Check run failure with output and annotations
        mock_run = MagicMock()
        mock_run.status = "completed"
        mock_run.conclusion = "failure"
        mock_run.name = "test-job"

        mock_output = MagicMock()
        mock_output.title = "Test Failed"
        mock_output.summary = "1 test failed"
        mock_run.output = mock_output

        mock_annotation = MagicMock()
        mock_annotation.message = "AssertionError: expected 1 got 2"
        mock_run.get_annotations.return_value = [mock_annotation]

        mock_commit.get_check_runs.return_value = [mock_run]

        result = self.agent.check_pipeline_status(mock_pr)
        self.assertFalse(result["success"])
        self.assertIn("Test Failed", result["details"])
        self.assertIn("AssertionError", result["details"])

    def test_check_pipeline_status_check_runs_billing_annotation(self):
        mock_pr = MagicMock()
        mock_commit = MagicMock()
        mock_pr.get_commits.return_value = MagicMock(totalCount=1, reversed=[mock_commit])

        mock_combined = MagicMock()
        mock_combined.state = "success"
        mock_commit.get_combined_status.return_value = mock_combined

        mock_run = MagicMock()
        mock_run.status = "completed"
        mock_run.conclusion = "failure"
        mock_run.name = "deploy-job"
        mock_run.output = None

        mock_annotation = MagicMock()
        mock_annotation.message = "Billing limit reached" # contains "billing"
        mock_run.get_annotations.return_value = [mock_annotation]

        mock_commit.get_check_runs.return_value = [mock_run]

        result = self.agent.check_pipeline_status(mock_pr)
        self.assertTrue(result["success"])

    def test_handle_pipeline_failure_ai_exception(self):
        mock_pr = MagicMock()
        mock_pr.number = 123
        self.mock_github.get_issue_comments.return_value = []

        # Mock AI client to raise exception
        self.agent.ai_client = MagicMock()
        self.agent.ai_client.generate_pr_comment.side_effect = Exception("AI Error")

        self.agent.handle_pipeline_failure(mock_pr, "details")

        # Should fallback to template
        mock_pr.create_issue_comment.assert_called()
        comment = mock_pr.create_issue_comment.call_args[0][0]
        self.assertIn("Pipeline Failure Detected", comment)
        self.assertIn("AI Error", self.agent.ai_client.generate_pr_comment.side_effect.args[0]) # Verify side effect happened

    def test_process_pr_author_safety(self):
        mock_pr = MagicMock()
        mock_pr.user.login = "untrusted_user"
        mock_pr.number = 123

        result = self.agent.process_pr(mock_pr)
        self.assertEqual(result["action"], "skipped")
        self.assertEqual(result["reason"], "unauthorized_author")

    def test_process_pr_google_suggestions_count(self):
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd" # trusted
        mock_pr.created_at = MagicMock() # Assuming age check passes via mock

        # Mock age check to pass
        with patch.object(self.agent, 'is_pr_too_young', return_value=False):
            # Mock suggestions applied
            self.mock_github.accept_review_suggestions.return_value = (True, "Applied", 2)

            # Mock mergeable=False to stop processing there
            mock_pr.mergeable = False
            with patch.object(self.agent, 'handle_conflicts') as mock_handle:
                mock_handle.return_value = {"action": "conflicts_detected"}
                self.agent.process_pr(mock_pr)
                # Verify logging happened (we can't easily check log output unless captured,
                # but we can verify execution flow didn't crash)

            # Mock suggestions failure
            self.mock_github.accept_review_suggestions.return_value = (False, "Error", 0)
            mock_pr.mergeable = False
            with patch.object(self.agent, 'handle_conflicts') as mock_handle:
                 mock_handle.return_value = {"action": "conflicts_detected"}
                 self.agent.process_pr(mock_pr)

    def test_process_pr_merge_failed(self):
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd"
        with patch.object(self.agent, 'is_pr_too_young', return_value=False):
            self.mock_github.accept_review_suggestions.return_value = (True, "OK", 0)
            mock_pr.mergeable = True

            # Pipeline success
            with patch.object(self.agent, 'check_pipeline_status', return_value={"success": True}):
                # Merge fails
                self.mock_github.merge_pr.return_value = (False, "Branch protection")
                result = self.agent.process_pr(mock_pr)
                self.assertEqual(result["action"], "merge_failed")

    def test_process_pr_label_failure(self):
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd"
        with patch.object(self.agent, 'is_pr_too_young', return_value=False):
            self.mock_github.accept_review_suggestions.return_value = (True, "OK", 0)
            mock_pr.mergeable = True

            # Pipeline success
            with patch.object(self.agent, 'check_pipeline_status', return_value={"success": True}):
                # Merge success
                self.mock_github.merge_pr.return_value = (True, "Merged")

                # Label failure mock
                self.mock_github.add_label_to_pr = MagicMock(return_value=(False, "Label Error"))

                result = self.agent.process_pr(mock_pr)
                self.assertEqual(result["action"], "merged")
                # Should log warning but still return merged

    def test_process_pr_comment_failure(self):
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd"
        with patch.object(self.agent, 'is_pr_too_young', return_value=False):
            self.mock_github.accept_review_suggestions.return_value = (True, "OK", 0)
            mock_pr.mergeable = True

            with patch.object(self.agent, 'check_pipeline_status', return_value={"success": True}):
                self.mock_github.merge_pr.return_value = (True, "Merged")
                self.mock_github.add_label_to_pr = MagicMock(return_value=(True, "OK"))

                # Comment failure
                self.mock_github.comment_on_pr.side_effect = Exception("Comment Error")

                result = self.agent.process_pr(mock_pr)
                self.assertEqual(result["action"], "merged")

    def test_notify_conflicts_check_comments_error(self):
        mock_pr = MagicMock()
        mock_pr.number = 123
        self.mock_github.get_issue_comments.side_effect = Exception("API Error")

        self.agent.notify_conflicts(mock_pr)
        # Should catch exception and proceed to post comment
        mock_pr.create_issue_comment.assert_called()

    def test_notify_conflicts_post_error(self):
        mock_pr = MagicMock()
        mock_pr.number = 123
        self.mock_github.get_issue_comments.return_value = []
        mock_pr.create_issue_comment.side_effect = Exception("Post Error")

        result = self.agent.notify_conflicts(mock_pr)
        self.assertEqual(result["action"], "conflicts_detected")

    def test_handle_pipeline_failure_check_comments_error(self):
        mock_pr = MagicMock()
        mock_pr.number = 123
        self.mock_github.get_issue_comments.side_effect = Exception("API Error")

        self.agent.ai_client = MagicMock()
        self.agent.ai_client.generate_pr_comment.return_value = "Comment"

        self.agent.handle_pipeline_failure(mock_pr, "details")
        mock_pr.create_issue_comment.assert_called()

if __name__ == '__main__':
    unittest.main()
