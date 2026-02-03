import unittest
from unittest.mock import MagicMock, patch
from src.agent import Agent

class TestAgent(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_ai = MagicMock()
        self.agent = Agent(self.mock_github, self.mock_ai, target_author="test-bot")

    def test_run_flow(self):
        # Mock search result
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.repository.full_name = "juninmd/test-repo"

        mock_pr = MagicMock()
        mock_pr.number = 1

        self.mock_github.search_prs.return_value = [mock_issue]
        self.mock_github.get_pr_from_issue.return_value = mock_pr

        # Mock process_pr calls
        with patch.object(self.agent, 'process_pr') as mock_process:
            self.agent.run()

            self.mock_github.search_prs.assert_called()
            self.mock_github.get_pr_from_issue.assert_called_with(mock_issue)
            mock_process.assert_called_with(mock_pr)

    def test_process_pr_clean_merge(self):
        pr = MagicMock()
        pr.number = 1
        pr.mergeable = True
        pr.user.login = "test-bot"

        # Mock commits and status
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "success"
        commit.get_combined_status.return_value = combined_status
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        self.agent.process_pr(pr)

        self.mock_github.merge_pr.assert_called_with(pr)

    def test_process_pr_pipeline_pending(self):
        pr = MagicMock()
        pr.number = 4
        pr.mergeable = True
        pr.user.login = "test-bot"

        # Mock commits and status
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "pending"
        commit.get_combined_status.return_value = combined_status
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        self.agent.process_pr(pr)

        # Should NOT merge, should NOT comment
        self.mock_github.merge_pr.assert_not_called()
        self.mock_github.comment_on_pr.assert_not_called()

    def test_process_pr_no_commits(self):
        pr = MagicMock()
        pr.number = 10
        pr.mergeable = True
        pr.user.login = "test-bot"

        # Mock 0 commits
        pr.get_commits.return_value.totalCount = 0

        self.agent.process_pr(pr)

        # Should NOT merge because pipeline_success is False
        self.mock_github.merge_pr.assert_not_called()

    def test_process_pr_pipeline_unknown_state(self):
        pr = MagicMock()
        pr.number = 11
        pr.mergeable = True
        pr.user.login = "test-bot"

        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "unknown_state"
        commit.get_combined_status.return_value = combined_status
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        self.agent.process_pr(pr)

        # Should NOT merge because state is not success
        self.mock_github.merge_pr.assert_not_called()

    def test_process_pr_pipeline_failure(self):
        pr = MagicMock()
        pr.number = 2
        pr.mergeable = True
        pr.user.login = "test-bot"

        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "failure"
        combined_status.description = "Build failed"
        commit.get_combined_status.return_value = combined_status
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        self.mock_ai.generate_pr_comment.return_value = "Please fix build."

        self.agent.process_pr(pr)

        self.mock_ai.generate_pr_comment.assert_called()
        self.mock_github.comment_on_pr.assert_called_with(pr, "Please fix build.")
        self.mock_github.merge_pr.assert_not_called()

    @patch("src.agent.subprocess")
    def test_handle_conflicts_logic(self, mock_subprocess):
        # Refined test for conflicts
        pr = MagicMock()
        pr.number = 3
        pr.mergeable = False
        pr.user.login = "test-bot"

        # Mocking the subprocess calls is complex because of the sequence
        # Instead, verify it calls handle_conflicts
        with patch.object(self.agent, 'handle_conflicts') as mock_handle:
            self.agent.process_pr(pr)
            mock_handle.assert_called_once_with(pr)

    def test_process_pr_wrong_author(self):
        pr = MagicMock()
        pr.number = 9
        pr.user.login = "other-user"

        self.agent.process_pr(pr)

        # Should do nothing
        self.mock_github.merge_pr.assert_not_called()

    def test_process_pr_mergeable_none(self):
        pr = MagicMock()
        pr.number = 99
        pr.user.login = "test-bot"
        pr.mergeable = None

        with patch("builtins.print") as mock_print:
            self.agent.process_pr(pr)
            mock_print.assert_any_call("PR #99 mergeability is unknown (GitHub is computing). Skipping.")

        # Should NOT merge, should NOT comment
        self.mock_github.merge_pr.assert_not_called()
        self.mock_github.comment_on_pr.assert_not_called()

    @patch("src.agent.subprocess")
    @patch("src.agent.os")
    def test_handle_conflicts_subprocess_calls(self, mock_os, mock_subprocess):
        # Setup PR data for a fork scenario
        pr = MagicMock()
        pr.number = 5
        pr.base.repo.full_name = "juninmd/repo"
        pr.head.repo.full_name = "fork-user/repo"
        pr.base.repo.clone_url = "https://github.com/juninmd/repo.git"
        pr.head.repo.clone_url = "https://github.com/fork-user/repo.git"
        pr.head.ref = "feature-branch"
        pr.base.ref = "main"

        # Mock token
        self.agent.github_client.token = "TEST_TOKEN"

        # Mock os.path.exists to return False so it doesn't try to rm first
        mock_os.path.exists.return_value = False

        # Mock subprocess to simulate clean merge (avoids conflict resolution logic loop)
        # This focuses on verifying the setup (clone, remote add, fetch)

        self.agent.handle_conflicts(pr)

        # Expected URL with token
        expected_head_url = "https://x-access-token:TEST_TOKEN@github.com/fork-user/repo.git"
        expected_base_url = "https://x-access-token:TEST_TOKEN@github.com/juninmd/repo.git"
        work_dir = f"/tmp/pr_juninmd_repo_{pr.number}"

        # Verify Clone (Head)
        mock_subprocess.run.assert_any_call(
            ["git", "clone", expected_head_url, work_dir],
            check=True, capture_output=True
        )

        # Verify Remote Add (Upstream/Base)
        mock_subprocess.run.assert_any_call(
            ["git", "remote", "add", "upstream", expected_base_url],
            cwd=work_dir, check=True
        )

        # Verify Fetch Upstream
        mock_subprocess.run.assert_any_call(
            ["git", "fetch", "upstream"],
            cwd=work_dir, check=True
        )

        # Verify Merge Upstream
        mock_subprocess.run.assert_any_call(
            ["git", "merge", "upstream/main"],
            cwd=work_dir, check=True, capture_output=True
        )

    @patch("src.agent.subprocess")
    def test_handle_conflicts_missing_head_repo(self, mock_subprocess):
        pr = MagicMock()
        pr.number = 6
        pr.base.repo.full_name = "juninmd/repo"
        pr.head.repo = None  # Simulate deleted fork
        pr.head.ref = "feature-branch"
        pr.base.ref = "main"

        with patch("builtins.print") as mock_print:
            self.agent.handle_conflicts(pr)
            mock_print.assert_any_call(f"PR #{pr.number} head repository is missing (deleted fork?). Skipping conflict resolution.")

        # Ensure no subprocess commands were run (no cloning)
        mock_subprocess.run.assert_not_called()

    def test_handle_pipeline_failure_duplicate_comment(self):
        pr = MagicMock()
        pr.number = 7
        pr.mergeable = True
        pr.user.login = "test-bot"

        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "failure"
        combined_status.description = "Build failed"
        commit.get_combined_status.return_value = combined_status
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        # Mock existing comments
        mock_comment = MagicMock()
        mock_comment.body = "Pipeline failed with status: Build failed. context: None"
        self.mock_github.get_issue_comments.return_value = [mock_comment]

        self.agent.process_pr(pr)

        self.mock_github.get_issue_comments.assert_called_with(pr)
        # Should NOT comment again
        self.mock_github.comment_on_pr.assert_not_called()
        self.mock_github.merge_pr.assert_not_called()

if __name__ == '__main__':
    unittest.main()
