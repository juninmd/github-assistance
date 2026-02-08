import unittest
from unittest.mock import MagicMock, patch
from src.agent import Agent

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
        # Ensure we are targeting the correct author and owner
        self.agent = Agent(self.mock_github, self.mock_ai, target_author="google-labs-jules", target_owner="juninmd")

    def test_rule_1_resolve_conflicts(self):
        """
        Rule 1: Caso exista conflitos de merge, você vai resolver tendo total autonomia fazendo os ajustes na mesma branch, fazendo push para resolver.
        """
        pr = MagicMock()
        pr.number = 1
        pr.user.login = "google-labs-jules"
        pr.mergeable = False # Indicates conflicts

        # Mocking the conflict resolution method since it involves subprocesses
        with patch.object(self.agent, 'handle_conflicts') as mock_handle_conflicts:
            self.agent.process_pr(pr)

            # Verify that conflict resolution was initiated
            mock_handle_conflicts.assert_called_once_with(pr)

    def test_rule_2_pipeline_issues(self):
        """
        Rule 2: Caso o pull request tenha problemas no pipeline, como não ter conseguido rodar testes ou build, você irá pedir para corrigir.
        """
        pr = MagicMock()
        pr.number = 2
        pr.user.login = "google-labs-jules"
        pr.mergeable = True

        # Simulate pipeline failure
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "failure"

        status_fail = MagicMock()
        status_fail.state = "failure"
        status_fail.context = "ci/tests"
        status_fail.description = "Tests failed"
        combined_status.statuses = [status_fail]

        commit.get_combined_status.return_value = combined_status
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        self.mock_ai.generate_pr_comment.return_value = "Please fix the pipeline issues."

        self.agent.process_pr(pr)

        # Verify that a comment was requested (asking for correction)
        self.mock_ai.generate_pr_comment.assert_called_with("Pipeline failed with status:\n- ci/tests: Tests failed")
        self.mock_github.comment_on_pr.assert_called_with(pr, "Please fix the pipeline issues.")

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

        # Simulate pipeline success
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "success"
        commit.get_combined_status.return_value = combined_status
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
        self.mock_github.comment_on_pr.assert_not_called()

if __name__ == '__main__':
    unittest.main()
