import unittest
from unittest.mock import MagicMock, patch, call
from src.agents.pr_assistant.agent import PRAssistantAgent

class TestRequirementsVerification(unittest.TestCase):
    """
    Verifies that the Agent complies with the specific rules for 'Jules da Google'.

    Rules:
    1. If opened by 'google-labs-jules' and has conflicts -> Resolve autonomously.
    2. If opened by 'google-labs-jules' and has pipeline issues -> Request correction.
    3. If opened by 'google-labs-jules' and is clean/success -> Auto-merge.
    """

    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_ai = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()

        # Ensure we are targeting the correct author and owner
        self.agent = PRAssistantAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            target_owner="juninmd",
            allowed_authors=["google-labs-jules"]
        )
        self.agent.ai_client = self.mock_ai

    def test_rule_1_resolve_conflicts(self):
        """
        Rule 1: Caso exista conflitos de merge, você vai resolver tendo total autonomia fazendo os ajustes na mesma branch, fazendo push para resolver.
        """
        pr = MagicMock()
        pr.number = 1
        pr.user.login = "google-labs-jules"
        pr.mergeable = False # Indicates conflicts

        # We verify that handle_conflicts is called, which then triggers autonomous resolution
        with patch.object(self.agent, 'handle_conflicts') as mock_handle_conflicts:
            self.agent.process_pr(pr)
            mock_handle_conflicts.assert_called_once_with(pr)

    def test_rule_2_pipeline_issues(self):
        """
        Rule 2: Caso o pull request tenha problemas no pipeline, como não ter conseguido rodar testes ou build, você irá pedir para corrigir.
        """
        pr = MagicMock()
        pr.number = 2
        pr.user.login = "google-labs-jules"
        pr.mergeable = True
        pr.title = "Fix"

        # Simulate pipeline failure
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "failure"

        status_fail = MagicMock()
        status_fail.state = "failure"
        status_fail.context = "ci/tests"
        status_fail.description = "Tests failed"
        combined_status.statuses = [status_fail]
        combined_status.total_count = 1

        commit.get_combined_status.return_value = combined_status
        commit.get_check_runs.return_value = []
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        # Mock existing comments
        self.mock_github.get_issue_comments.return_value = []

        self.mock_ai.generate_pr_comment.return_value = "Please fix the pipeline issues."

        self.agent.process_pr(pr)

        # Verify that a comment was requested (asking for correction)
        # Note: PRAssistantAgent calls pr.create_issue_comment directly
        pr.create_issue_comment.assert_called_with("Please fix the pipeline issues.")

        # Verify no merge happened
        self.mock_github.merge_pr.assert_not_called()

    def test_rule_3_auto_merge(self):
        """
        Rule 3: Caso o pull request tenha passado no pipeline com sucesso, não tenha conflito de merge, você irá realizar os merges automaticamente.
        """
        pr = MagicMock()
        pr.number = 3
        pr.user.login = "google-labs-jules"
        pr.mergeable = True # No conflicts
        pr.title = "Fix"

        # Simulate pipeline success
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "success"
        commit.get_combined_status.return_value = combined_status
        commit.get_check_runs.return_value = []
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        self.mock_github.merge_pr.return_value = (True, "Merged")
        self.agent.process_pr(pr)

        # Verify auto-merge
        self.mock_github.merge_pr.assert_called_once_with(pr)

    def test_ignore_other_authors(self):
        """
        Implicit Rule: Only act on PRs from 'Jules da Google' (google-labs-jules).
        """
        pr = MagicMock()
        pr.number = 4
        pr.user.login = "other-developer"
        pr.mergeable = True

        # Even if it is successful
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "success"
        commit.get_combined_status.return_value = combined_status
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        self.agent.process_pr(pr)

        # Verify NO action
        self.mock_github.merge_pr.assert_not_called()
        pr.create_issue_comment.assert_not_called()

if __name__ == '__main__':
    unittest.main()
