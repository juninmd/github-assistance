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
        self.agent = PRAssistantAgent(self.mock_github, self.mock_jules, self.mock_allowlist)

    def test_report_pr_statuses(self):
        # 1. Clean PR (Success)
        pr_clean = MagicMock()
        pr_clean.number = 101
        pr_clean.title = "Clean PR"
        pr_clean.user.login = "google-labs-jules"
        pr_clean.mergeable = True
        pr_clean.base.repo.full_name = "juninmd/repo1"
        commit_clean = MagicMock()
        commit_clean.get_combined_status.return_value.state = "success"
        pr_clean.get_commits.return_value.reversed = [commit_clean]
        pr_clean.get_commits.return_value.totalCount = 1

        # 2. Conflict PR
        pr_conflict = MagicMock()
        pr_conflict.number = 102
        pr_conflict.title = "Conflict PR"
        pr_conflict.user.login = "google-labs-jules"
        pr_conflict.mergeable = False
        pr_conflict.base.repo.full_name = "juninmd/repo2"

        # 3. Failed PR
        pr_failed = MagicMock()
        pr_failed.number = 103
        pr_failed.title = "Failed PR"
        pr_failed.user.login = "google-labs-jules"
        pr_failed.mergeable = True
        pr_failed.base.repo.full_name = "juninmd/repo3"
        commit_failed = MagicMock()
        commit_failed.get_combined_status.return_value.state = "failure"
        s = MagicMock()
        s.state = "failure"
        s.context = "ci/test"
        s.description = "Unit tests failed"
        commit_failed.get_combined_status.return_value.statuses = [s]
        pr_failed.get_commits.return_value.reversed = [commit_failed]
        pr_failed.get_commits.return_value.totalCount = 1

        # 4. Pending PR
        pr_pending = MagicMock()
        pr_pending.number = 104
        pr_pending.title = "Pending PR"
        pr_pending.user.login = "google-labs-jules"
        pr_pending.mergeable = True
        pr_pending.base.repo.full_name = "juninmd/repo4"
        commit_pending = MagicMock()
        commit_pending.get_combined_status.return_value.state = "pending"
        pr_pending.get_commits.return_value.reversed = [commit_pending]
        pr_pending.get_commits.return_value.totalCount = 1

        # 5. Wrong Author
        pr_other = MagicMock()
        pr_other.number = 105
        pr_other.title = "Other PR"
        pr_other.user.login = "random-user"
        pr_other.base.repo.full_name = "juninmd/repo5"

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

        self.mock_github.search_prs.return_value = issues

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

        # Mock side effects to avoid complex logic
        with patch.object(self.agent, 'handle_conflicts') as mock_conflicts, \
             patch.object(self.agent, 'handle_pipeline_failure') as mock_fail, \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:

            self.agent.run()

            output = mock_stdout.getvalue()

            # Assertions
            self.assertIn("Processing PR #101", output)
            self.assertIn("PR #101 is clean and pipeline passed. Merging...", output)

            self.assertIn("Processing PR #102", output)
            self.assertIn("PR #102 has conflicts.", output)

            self.assertIn("Processing PR #103", output)
            self.assertIn("PR #103 has pipeline failures.", output)

            self.assertIn("Processing PR #104", output)
            self.assertIn("pipeline is 'pending'. Skipping.", output)

            self.assertIn("Processing PR #105", output)
            self.assertIn("Skipping PR #105 from author random-user", output)

if __name__ == '__main__':
    unittest.main()
