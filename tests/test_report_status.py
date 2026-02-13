import unittest
from unittest.mock import MagicMock, patch
import io
import sys
from src.agents.pr_assistant.agent import PRAssistantAgent

class TestPRStatusReporting(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True
        # Fix constructor order: jules, github, allowlist
        self.agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist, allowed_authors=["google-labs-jules"])

    def test_report_pr_statuses(self):
        # 1. Clean PR (Success)
        pr_clean = MagicMock()
        pr_clean.number = 101
        pr_clean.title = "Clean PR"
        pr_clean.user.login = "google-labs-jules"
        pr_clean.mergeable = True
        pr_clean.draft = False
        pr_clean.base.repo.full_name = "juninmd/repo1"
        commit_clean = MagicMock()
        commit_clean.get_combined_status.return_value.state = "success"
        commit_clean.get_check_runs.return_value = []
        pr_clean.get_commits.return_value.reversed = [commit_clean]
        pr_clean.get_commits.return_value.totalCount = 1

        # 2. Conflict PR
        pr_conflict = MagicMock()
        pr_conflict.number = 102
        pr_conflict.title = "Conflict PR"
        pr_conflict.user.login = "google-labs-jules"
        pr_conflict.mergeable = False
        pr_conflict.draft = False
        pr_conflict.base.repo.full_name = "juninmd/repo2"

        # 3. Failed PR
        pr_failed = MagicMock()
        pr_failed.number = 103
        pr_failed.title = "Failed PR"
        pr_failed.user.login = "google-labs-jules"
        pr_failed.mergeable = True
        pr_failed.draft = False
        pr_failed.base.repo.full_name = "juninmd/repo3"
        commit_failed = MagicMock()
        commit_failed.get_combined_status.return_value.state = "failure"
        s = MagicMock()
        s.state = "failure"
        s.context = "ci/test"
        s.description = "Unit tests failed"
        commit_failed.get_combined_status.return_value.statuses = [s]
        commit_failed.get_combined_status.return_value.total_count = 1
        commit_failed.get_check_runs.return_value = []
        pr_failed.get_commits.return_value.reversed = [commit_failed]
        pr_failed.get_commits.return_value.totalCount = 1

        # 4. Pending PR
        pr_pending = MagicMock()
        pr_pending.number = 104
        pr_pending.title = "Pending PR"
        pr_pending.user.login = "google-labs-jules"
        pr_pending.mergeable = True
        pr_pending.draft = False
        pr_pending.base.repo.full_name = "juninmd/repo4"
        commit_pending = MagicMock()
        commit_pending.get_combined_status.return_value.state = "pending"
        commit_pending.get_combined_status.return_value.total_count = 1
        commit_pending.get_check_runs.return_value = []
        pr_pending.get_commits.return_value.reversed = [commit_pending]
        pr_pending.get_commits.return_value.totalCount = 1

        # 5. Wrong Author
        pr_other = MagicMock()
        pr_other.number = 105
        pr_other.title = "Other PR"
        pr_other.user.login = "random-user"
        pr_other.draft = False
        pr_other.base.repo.full_name = "juninmd/repo5"

        issues_list = [MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        issues_list[0].number = 101
        issues_list[0].repository.full_name = "juninmd/repo1"
        issues_list[0].title = "Clean PR"

        issues_list[1].number = 102
        issues_list[1].repository.full_name = "juninmd/repo2"
        issues_list[1].title = "Conflict PR"

        issues_list[2].number = 103
        issues_list[2].repository.full_name = "juninmd/repo3"
        issues_list[2].title = "Failed PR"

        issues_list[3].number = 104
        issues_list[3].repository.full_name = "juninmd/repo4"
        issues_list[3].title = "Pending PR"

        issues_list[4].number = 105
        issues_list[4].repository.full_name = "juninmd/repo5"
        issues_list[4].title = "Other PR"

        # Mock issues object with totalCount
        issues_obj = MagicMock()
        issues_obj.totalCount = 5
        issues_obj.__iter__.return_value = iter(issues_list)
        self.mock_github.search_prs.return_value = issues_obj

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

        # Ensure merge_pr returns a tuple
        self.mock_github.merge_pr.return_value = (True, "Merged")

        # Mock side effects to avoid complex logic
        # Also need to mock self.log to verify messages, since captured stdout logic is flaky with mock_stdout context vs direct print

        # But wait, self.log uses print.
        # If I patch sys.stdout, print calls are captured.
        # The previous failure was because search_prs returned a list without totalCount, so it crashed before printing specific PR logs.

        with patch.object(self.agent, 'handle_conflicts') as mock_conflicts, \
             patch.object(self.agent, 'handle_pipeline_failure') as mock_fail, \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:

            self.agent.run()

            output = mock_stdout.getvalue()

            # Assertions - Check logic flow by verifying calls or logs
            self.assertIn("Processing PR #101", output)
            self.assertIn("ready to merge", output)

            self.assertIn("Processing PR #102", output)
            self.assertIn("has conflicts", output)
            mock_conflicts.assert_called_with(pr_conflict)

            self.assertIn("Processing PR #103", output)
            self.assertIn("has pipeline failures", output)
            mock_fail.assert_called() # With details

            self.assertIn("Processing PR #104", output)
            self.assertIn("pipeline is pending", output)

            self.assertIn("Processing PR #105", output)
            self.assertIn("Skipping PR #105 from author random-user", output)

if __name__ == '__main__':
    unittest.main()
