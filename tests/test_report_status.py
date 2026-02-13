import unittest
from unittest.mock import MagicMock, patch
import io
import sys
from datetime import datetime, timezone, timedelta
from src.agents.pr_assistant.agent import PRAssistantAgent

class TestPRStatusReporting(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True

        # Patch AI client
        with patch("src.agents.pr_assistant.agent.GeminiClient"):
            self.agent = PRAssistantAgent(
                self.mock_jules,
                self.mock_github,
                self.mock_allowlist,
                target_owner="juninmd",
                allowed_authors=["google-labs-jules"]
            )
        self.agent.ai_client = MagicMock()

    def test_report_pr_statuses(self):
        # Create a timestamp for all PRs (15 minutes ago - older than min age)
        pr_created_time = datetime.now(timezone.utc) - timedelta(minutes=15)
        
        # 1. Clean PR (Success)
        pr_clean = MagicMock()
        pr_clean.number = 101
        pr_clean.draft = False
        pr_clean.title = "Clean PR"
        pr_clean.user.login = "google-labs-jules"
        pr_clean.mergeable = True
        pr_clean.base.repo.full_name = "juninmd/repo1"
        pr_clean.created_at = pr_created_time
        commit_clean = MagicMock()
        commit_clean.get_combined_status.return_value.state = "success"
        commit_clean.get_check_runs.return_value = []
        pr_clean.get_commits.return_value.reversed = [commit_clean]
        pr_clean.get_commits.return_value.totalCount = 1

        # 2. Conflict PR
        pr_conflict = MagicMock()
        pr_conflict.number = 102
        pr_conflict.draft = False
        pr_conflict.title = "Conflict PR"
        pr_conflict.user.login = "google-labs-jules"
        pr_conflict.mergeable = False
        pr_conflict.base.repo.full_name = "juninmd/repo2"
        pr_conflict.created_at = pr_created_time

        # 3. Failed PR
        pr_failed = MagicMock()
        pr_failed.number = 103
        pr_failed.draft = False
        pr_failed.title = "Failed PR"
        pr_failed.user.login = "google-labs-jules"
        pr_failed.mergeable = True
        pr_failed.base.repo.full_name = "juninmd/repo3"
        pr_failed.created_at = pr_created_time
        commit_failed = MagicMock()
        commit_failed.get_combined_status.return_value.state = "failure"
        s = MagicMock()
        s.state = "failure"
        s.context = "ci/test"
        s.description = "Unit tests failed"
        commit_failed.get_combined_status.return_value.statuses = [s]
        combined_status_failed = commit_failed.get_combined_status.return_value
        combined_status_failed.total_count = 1

        commit_failed.get_check_runs.return_value = []
        pr_failed.get_commits.return_value.reversed = [commit_failed]
        pr_failed.get_commits.return_value.totalCount = 1

        # 4. Pending PR
        pr_pending = MagicMock()
        pr_pending.number = 104
        pr_pending.draft = False
        pr_pending.title = "Pending PR"
        pr_pending.user.login = "google-labs-jules"
        pr_pending.mergeable = True
        pr_pending.base.repo.full_name = "juninmd/repo4"
        pr_pending.created_at = pr_created_time
        commit_pending = MagicMock()
        commit_pending.get_combined_status.return_value.state = "pending"
        commit_pending.get_combined_status.return_value.total_count = 1
        commit_pending.get_check_runs.return_value = []
        pr_pending.get_commits.return_value.reversed = [commit_pending]
        pr_pending.get_commits.return_value.totalCount = 1

        # 5. Wrong Author
        pr_other = MagicMock()
        pr_other.number = 105
        pr_other.draft = False
        pr_other.title = "Other PR"
        pr_other.user.login = "random-user"
        pr_other.base.repo.full_name = "juninmd/repo5"
        pr_other.created_at = pr_created_time
        
        # Mock accept_review_suggestions for all PRs
        self.mock_github.accept_review_suggestions.return_value = (True, "No suggestions", 0)

        issues = [MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        issues[0].number = 101
        issues[0].repository.full_name = "juninmd/repo1"
        issues[0].title = "Clean PR"

        issues[1].number = 102
        issues[1].repository.full_name = "juninmd/repo2"
        issues[1].title = "Conflict PR"

        issues[2].number = 103
        issues[2].repository.full_name = "juninmd/repo3"
        issues[2].title = "Failed PR"

        issues[3].number = 104
        issues[3].repository.full_name = "juninmd/repo4"
        issues[3].title = "Pending PR"

        issues[4].number = 105
        issues[4].repository.full_name = "juninmd/repo5"
        issues[4].title = "Other PR"

        # Fix: Search result must have totalCount and be iterable
        mock_issues_result = MagicMock()
        mock_issues_result.totalCount = 5
        mock_issues_result.__iter__.return_value = iter(issues)
        self.mock_github.search_prs.return_value = mock_issues_result

        def get_pr_side_effect(issue):
            mapping = {
                101: pr_clean,
                102: pr_conflict,
                103: pr_failed,
                104: pr_pending,
                105: pr_other
            }
            return mapping[issue.number]

        self.mock_github.get_pr_from_issue.side_effect = get_pr_side_effect
        self.mock_github.merge_pr.return_value = (True, "Merged")

        # Mock side effects to avoid complex logic
        with patch.object(self.agent, 'handle_conflicts') as mock_conflicts, \
             patch.object(self.agent, 'handle_pipeline_failure') as mock_fail, \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:

            self.agent.run()

            output = mock_stdout.getvalue()

            # Assertions - Updated to match actual log messages
            self.assertIn("Processing PR #101", output)
            self.assertIn("PR #101 is ready to merge", output)

            self.assertIn("Processing PR #102", output)
            self.assertIn("PR #102 has conflicts", output)

            self.assertIn("Processing PR #103", output)
            self.assertIn("PR #103 has pipeline failures", output)

            self.assertIn("Processing PR #104", output)
            self.assertIn("pipeline is pending", output)

            self.assertIn("Processing PR #105", output)
            self.assertIn("Skipping PR #105 from author random-user", output)

if __name__ == '__main__':
    unittest.main()
