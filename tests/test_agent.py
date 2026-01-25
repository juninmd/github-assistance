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

if __name__ == '__main__':
    unittest.main()
