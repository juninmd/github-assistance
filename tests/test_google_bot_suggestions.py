import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from src.agents.pr_assistant.agent import PRAssistantAgent
from src.github_client import GithubClient


class TestGoogleBotSuggestions(unittest.TestCase):
    """Test Google bot review suggestion acceptance and PR age checks."""

    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True

        with patch("src.agents.pr_assistant.agent.get_ai_client"):
            self.agent = PRAssistantAgent(
                self.mock_jules,
                self.mock_github,
                self.mock_allowlist
            )
            self.agent.ai_client = MagicMock()

    def test_is_pr_too_young_returns_true(self):
        """Test that a PR created < 10 minutes ago is too young."""
        pr = MagicMock()
        # PR created 5 minutes ago
        pr.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        result = self.agent.is_pr_too_young(pr)
        self.assertTrue(result)

    def test_is_pr_too_young_returns_false(self):
        """Test that a PR created > 10 minutes ago is not too young."""
        pr = MagicMock()
        # PR created 15 minutes ago
        pr.created_at = datetime.now(timezone.utc) - timedelta(minutes=15)

        result = self.agent.is_pr_too_young(pr)
        self.assertFalse(result)

    def test_is_pr_too_young_exactly_10_minutes(self):
        """Test that a PR created exactly 10 minutes ago is not too young."""
        pr = MagicMock()
        # PR created exactly 10 minutes ago
        pr.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)

        result = self.agent.is_pr_too_young(pr)
        self.assertFalse(result)

    def test_is_pr_too_young_with_naive_datetime(self):
        """Test that naive datetime is handled correctly."""
        pr = MagicMock()
        # PR created 5 minutes ago without timezone
        pr.created_at = datetime.now() - timedelta(minutes=5)
        # Remove timezone info to make it naive
        pr.created_at = pr.created_at.replace(tzinfo=None)

        result = self.agent.is_pr_too_young(pr)
        self.assertTrue(result)

    def test_process_pr_skips_young_pr(self):
        """Test that process_pr skips PRs that are too young."""
        pr = MagicMock()
        pr.user.login = "juninmd"
        pr.title = "Test PR"
        pr.number = 123
        pr.base.repo.full_name = "owner/repo"
        # PR created 3 minutes ago
        pr.created_at = datetime.now(timezone.utc) - timedelta(minutes=3)

        result = self.agent.process_pr(pr)

        self.assertEqual(result["action"], "skipped")
        self.assertIn("pr_too_young", result["reason"])
        self.assertEqual(result["pr"], 123)

    def test_process_pr_processes_old_pr(self):
        """Test that process_pr continues with PRs older than 10 minutes."""
        pr = MagicMock()
        pr.user.login = "juninmd"
        pr.title = "Test PR"
        pr.number = 123
        pr.base.repo.full_name = "owner/repo"
        pr.mergeable = True
        # PR created 15 minutes ago
        pr.created_at = datetime.now(timezone.utc) - timedelta(minutes=15)

        # Mock accept_review_suggestions to return no suggestions
        self.mock_github.accept_review_suggestions.return_value = (True, "No suggestions", 0)

        # Mock pipeline check to succeed
        with patch.object(self.agent, 'check_pipeline_status', return_value={"success": True}):
            # Mock merge to succeed
            self.mock_github.merge_pr.return_value = (True, "Merged")

            result = self.agent.process_pr(pr)

            # Should proceed to merge
            self.assertEqual(result["action"], "merged")
            self.assertEqual(result["pr"], 123)

    def test_process_pr_applies_google_bot_suggestions(self):
        """Test that process_pr applies Google bot suggestions."""
        pr = MagicMock()
        pr.user.login = "google-labs-jules"
        pr.title = "Test PR"
        pr.number = 456
        pr.base.repo.full_name = "owner/repo"
        pr.mergeable = True
        # PR created 15 minutes ago
        pr.created_at = datetime.now(timezone.utc) - timedelta(minutes=15)

        # Mock accept_review_suggestions to return 2 suggestions applied
        self.mock_github.accept_review_suggestions.return_value = (True, "Applied 2 suggestions", 2)

        # Mock pipeline check to succeed
        with patch.object(self.agent, 'check_pipeline_status', return_value={"success": True}):
            # Mock merge to succeed
            self.mock_github.merge_pr.return_value = (True, "Merged")

            result = self.agent.process_pr(pr)
            print(f"DEBUG: result={result}")

            # Verify accept_review_suggestions was called with correct parameters
            self.mock_github.accept_review_suggestions.assert_called_once_with(
                pr,
                ["Jules da Google", "google-labs-jules", "gemini-code-assist"]
            )

            # Should proceed to merge
            self.assertEqual(result["action"], "merged")

    def test_google_bot_usernames_configured(self):
        """Test that Google bot usernames are properly configured."""
        self.assertIn("Jules da Google", self.agent.google_bot_usernames)
        self.assertIn("google-labs-jules", self.agent.google_bot_usernames)

    def test_min_pr_age_configured(self):
        """Test that minimum PR age is configured to 10 minutes."""
        self.assertEqual(self.agent.min_pr_age_minutes, 10)

    def test_process_pr_comments_acceptance_when_trusted_author_has_commit_suggestion(self):
        """Trusted author + commit suggestion in PR body should post acceptance comment."""
        pr = MagicMock()
        pr.user.login = "juninmd"
        pr.title = "Test PR"
        pr.number = 789
        pr.base.repo.full_name = "owner/repo"
        pr.body = "Commit suggestion: please apply this improvement"
        pr.mergeable = True
        pr.created_at = datetime.now(timezone.utc) - timedelta(minutes=15)

        self.mock_github.accept_review_suggestions.return_value = (True, "No suggestions", 0)

        with patch.object(self.agent, 'check_pipeline_status', return_value={"success": True}):
            self.mock_github.merge_pr.return_value = (True, "Merged")
            result = self.agent.process_pr(pr)

        self.assertEqual(result["action"], "merged")
        self.assertTrue(self.mock_github.comment_on_pr.call_count >= 2)
        first_call_message = self.mock_github.comment_on_pr.call_args_list[0].args[1]
        self.assertIn("aceita automaticamente", first_call_message)

    def test_process_pr_comments_rejection_when_untrusted_author_has_commit_suggestion(self):
        """Untrusted author + commit suggestion in PR body should post rejection comment and skip."""
        pr = MagicMock()
        pr.user.login = "random-user"
        pr.title = "Test PR"
        pr.number = 790
        pr.base.repo.full_name = "owner/repo"
        pr.body = "Sugestão de commit: troque o fluxo"

        result = self.agent.process_pr(pr)

        self.assertEqual(result["action"], "skipped")
        self.assertEqual(result["reason"], "unauthorized_author")
        self.mock_github.comment_on_pr.assert_called_once()
        self.assertIn("será rejeitada", self.mock_github.comment_on_pr.call_args.args[1])


class TestGithubClientReviewSuggestions(unittest.TestCase):
    """Test GithubClient review suggestion acceptance methods."""

    def setUp(self):
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'fake_token'}):
            self.client = GithubClient()

    def test_accept_review_suggestions_no_suggestions(self):
        """Test accept_review_suggestions when there are no suggestions."""
        pr = MagicMock()
        pr.get_review_comments.return_value = []

        success, msg, count = self.client.accept_review_suggestions(pr, ["Jules da Google"])

        self.assertTrue(success)
        self.assertEqual(count, 0)
        self.assertIn("No suggestions", msg)

    def test_accept_review_suggestions_from_non_bot(self):
        """Test that suggestions from non-bot users are ignored."""
        pr = MagicMock()

        comment = MagicMock()
        comment.user.login = "random-user"
        comment.body = "```suggestion\nsome code\n```"

        pr.get_review_comments.return_value = [comment]

        success, msg, count = self.client.accept_review_suggestions(pr, ["Jules da Google"])

        self.assertTrue(success)
        self.assertEqual(count, 0)

    def test_accept_review_suggestions_from_google_bot(self):
        """Test that suggestions from Google bot are processed."""
        pr = MagicMock()

        # Mock review comment
        comment = MagicMock()
        comment.user.login = "Jules da Google"
        comment.body = "```suggestion\nnew code here\n```"
        comment.path = "test.py"
        comment.line = 5
        comment.start_line = None

        # Mock file content
        file_content = MagicMock()
        file_content.decoded_content = b"line1\nline2\nline3\nline4\nold code\nline6\n"
        file_content.sha = "abc123"

        pr.head.repo.get_contents.return_value = file_content
        pr.head.ref = "feature-branch"
        pr.get_review_comments.return_value = [comment]

        success, msg, count = self.client.accept_review_suggestions(pr, ["Jules da Google"])

        # Should attempt to apply suggestion
        self.assertTrue(success)
        self.assertEqual(count, 1)
        self.assertIn("Applied 1", msg)

    def test_accept_review_suggestions_multiline(self):
        """Test accepting suggestions for multiple lines."""
        pr = MagicMock()

        # Mock review comment with multiline suggestion
        comment = MagicMock()
        comment.user.login = "google-labs-jules"
        comment.body = "```suggestion\nnew line 1\nnew line 2\n```"
        comment.path = "test.py"
        comment.line = 6
        comment.start_line = 5  # Lines 5-6

        # Mock file content
        file_content = MagicMock()
        file_content.decoded_content = b"line1\nline2\nline3\nline4\nold line 5\nold line 6\nline7\n"
        file_content.sha = "abc123"

        pr.head.repo.get_contents.return_value = file_content
        pr.head.ref = "feature-branch"
        pr.get_review_comments.return_value = [comment]

        success, msg, count = self.client.accept_review_suggestions(pr, ["google-labs-jules"])

        # Should apply suggestion
        self.assertTrue(success)
        self.assertEqual(count, 1)

    def test_accept_review_suggestions_exception_handling(self):
        """Test that exceptions during suggestion application are handled."""
        pr = MagicMock()

        comment = MagicMock()
        comment.user.login = "Jules da Google"
        comment.body = "```suggestion\nnew code\n```"
        comment.path = "test.py"

        pr.get_review_comments.return_value = [comment]
        # Make get_contents raise an exception
        pr.head.repo.get_contents.side_effect = Exception("File not found")

        success, msg, count = self.client.accept_review_suggestions(pr, ["Jules da Google"])

        # Should handle error gracefully
        self.assertTrue(success)
        self.assertEqual(count, 0)

    def test_accept_review_suggestions_no_suggestion_block(self):
        """Test that comments without suggestion blocks are ignored."""
        pr = MagicMock()

        comment = MagicMock()
        comment.user.login = "Jules da Google"
        comment.body = "This is just a regular comment without suggestions"

        pr.get_review_comments.return_value = [comment]

        success, msg, count = self.client.accept_review_suggestions(pr, ["Jules da Google"])

        self.assertTrue(success)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
