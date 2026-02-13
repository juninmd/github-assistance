import unittest
from unittest.mock import MagicMock, patch
import io
import sys
from src.agents.pr_assistant.agent import PRAssistantAgent

class TestJuninmdIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True
        # Fix constructor order
        self.agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist, allowed_authors=["google-labs-jules"])
        # Mock AI client to avoid initialization warning/error and allow testing AI features
        self.agent.ai_client = MagicMock()

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
        pr.draft = False
        pr.base.repo.full_name = repo_name
        pr.head.ref = f"feature-branch-{number}"
        pr.base.ref = "main"

        # Mock Commits and Status
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = status_state

        if status_state in ['failure', 'error']:
            s = MagicMock()
            s.state = status_state
            s.context = "ci/run"
            s.description = f"Status is {status_state}"
            combined_status.statuses = [s]
            combined_status.total_count = 1
        else:
            combined_status.statuses = []
            if status_state == "success":
                combined_status.total_count = 1 # success implies checks ran

        if status_state == "pending":
             combined_status.total_count = 1

        commit.get_combined_status.return_value = combined_status
        commit.get_check_runs.return_value = []

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
        issues_list = [issue1, issue2, issue3, issue4, issue5]
        issues_obj = MagicMock()
        issues_obj.totalCount = 5
        issues_obj.__iter__.return_value = iter(issues_list)
        self.mock_github.search_prs.return_value = issues_obj

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

        # Mock merge success
        self.mock_github.merge_pr.return_value = (True, "Merged")

        # Mock AI comment generation
        self.agent.ai_client.generate_pr_comment.return_value = "AI generated comment about failure."

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
            self.assertIn("ready to merge", output)

            # Check PR #2: Pipeline Failure
            # PRAssistantAgent calls pr.create_issue_comment
            pr2.create_issue_comment.assert_called_with("AI generated comment about failure.")
            self.assertIn("PR #102 has pipeline failures", output)

            # Check PR #3: Conflicts
            mock_handle_conflicts.assert_called_with(pr3)
            self.assertIn("PR #103 has conflicts", output)

            # Check PR #4: Pending
            self.assertIn("pipeline is pending", output)

            # Check PR #5: Wrong Author
            self.assertIn("Skipping PR #105 from author other-dev", output)

            # Check General
            self.assertIn("Scanning for PRs with query:", output)
            self.assertIn("user:juninmd", output)

if __name__ == '__main__':
    unittest.main()
