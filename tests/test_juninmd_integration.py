import unittest
from unittest.mock import MagicMock, patch
import io
import sys
from src.agent import Agent

class TestJuninmdIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_ai = MagicMock()
        self.agent = Agent(self.mock_github, self.mock_ai, target_owner="juninmd")

    def create_mock_pr(self, number, author, mergeable=True, status_state="success", repo_name="juninmd/repo"):
        # Mock Issue
        issue = MagicMock()
        issue.number = number
        issue.repository.full_name = repo_name
        issue.title = f"PR #{number}"

        # Mock PullRequest
        pr = MagicMock()
        pr.number = number
        pr.user.login = author
        pr.mergeable = mergeable
        pr.base.repo.full_name = repo_name
        pr.head.ref = f"feature-branch-{number}"
        pr.base.ref = "main"

        # Mock Commits and Status
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = status_state
        combined_status.description = f"Status is {status_state}"
        commit.get_combined_status.return_value = combined_status

        commits = MagicMock()
        commits.totalCount = 1
        commits.reversed = [commit]
        pr.get_commits.return_value = commits

        return issue, pr

    def test_juninmd_pr_processing(self):
        # Create different PR scenarios
        # 1. Success -> Merge
        issue1, pr1 = self.create_mock_pr(101, "google-labs-jules", mergeable=True, status_state="success")

        # 2. Failure -> Comment
        issue2, pr2 = self.create_mock_pr(102, "google-labs-jules", mergeable=True, status_state="failure")

        # 3. Conflict -> Resolve
        issue3, pr3 = self.create_mock_pr(103, "google-labs-jules", mergeable=False)

        # 4. Pending -> Skip
        issue4, pr4 = self.create_mock_pr(104, "google-labs-jules", mergeable=True, status_state="pending")

        # 5. Wrong Author -> Skip
        issue5, pr5 = self.create_mock_pr(105, "other-dev", mergeable=True, status_state="success")

        # Setup search_prs to return the issues
        self.mock_github.search_prs.return_value = [issue1, issue2, issue3, issue4, issue5]

        # Setup get_pr_from_issue to return the corresponding PRs
        # Side effect to return the correct PR based on the issue argument
        def get_pr_side_effect(issue):
            mapping = {
                101: pr1,
                102: pr2,
                103: pr3,
                104: pr4,
                105: pr5
            }
            return mapping[issue.number]

        self.mock_github.get_pr_from_issue.side_effect = get_pr_side_effect

        # Mock handle_conflicts because it involves subprocesses
        with patch.object(self.agent, 'handle_conflicts') as mock_handle_conflicts:
            # Capture stdout
            captured_output = io.StringIO()
            sys.stdout = captured_output

            try:
                self.agent.run()
            finally:
                sys.stdout = sys.__stdout__

            output = captured_output.getvalue()

            # Verifications

            # Check PR #1: Merged
            self.mock_github.merge_pr.assert_called_with(pr1)
            self.assertIn("PR #101 is clean and pipeline passed. Merging...", output)

            # Check PR #2: Pipeline Failure
            self.mock_github.comment_on_pr.assert_called_with(pr2, self.mock_ai.generate_pr_comment.return_value)
            self.assertIn("PR #102 has pipeline failures.", output)

            # Check PR #3: Conflicts
            mock_handle_conflicts.assert_called_with(pr3)
            self.assertIn("PR #103 has conflicts.", output)

            # Check PR #4: Pending
            self.assertIn("PR #104 pipeline is 'pending'. Skipping.", output)

            # Check PR #5: Wrong Author
            self.assertIn("Skipping PR #105 from author other-dev", output)

            # Check General
            self.assertIn("Scanning for PRs with query:", output)
            self.assertIn("user:juninmd", output)

if __name__ == '__main__':
    unittest.main()
