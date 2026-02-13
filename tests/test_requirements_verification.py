import unittest
from unittest.mock import MagicMock, patch
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
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True

        with patch("src.agents.pr_assistant.agent.GeminiClient"):
            self.agent = PRAssistantAgent(
                self.mock_jules,
                self.mock_github,
                self.mock_allowlist,
                target_owner="juninmd",
                allowed_authors=["google-labs-jules"]
            )
        # Mock AI client
        self.agent.ai_client = MagicMock()

    def test_rule_1_resolve_conflicts(self):
        """
        Rule 1: Caso exista conflitos de merge, você vai resolver tendo total autonomia fazendo os ajustes na mesma branch, fazendo push para resolver.
        """
        pr = MagicMock()
        pr.number = 1
        pr.user.login = "google-labs-jules"
        pr.mergeable = False # Indicates conflicts
        pr.base.repo.full_name = "juninmd/repo"
        # Mock PR created 15 minutes ago (older than min age)
        from datetime import datetime, timezone, timedelta
        pr.created_at = datetime.now(timezone.utc) - timedelta(minutes=15)
        
        # Mock accept_review_suggestions
        self.mock_github.accept_review_suggestions.return_value = (True, "No suggestions", 0)

        # Mocking resolve_conflicts_autonomously
        with patch.object(self.agent, 'resolve_conflicts_autonomously') as mock_resolve:
            self.agent.process_pr(pr)

            # Verify that conflict resolution was initiated autonomously
            mock_resolve.assert_called_once_with(pr)

    def test_rule_2_pipeline_issues(self):
        """
        Rule 2: Caso o pull request tenha problemas no pipeline, como não ter conseguido rodar testes ou build, você irá pedir para corrigir.
        """
        pr = MagicMock()
        pr.number = 2
        pr.user.login = "google-labs-jules"
        pr.mergeable = True
        pr.base.repo.full_name = "juninmd/repo"
        # Mock PR created 15 minutes ago (older than min age)
        from datetime import datetime, timezone, timedelta
        pr.created_at = datetime.now(timezone.utc) - timedelta(minutes=15)

        # Mock accept_review_suggestions
        self.mock_github.accept_review_suggestions.return_value = (True, "No suggestions", 0)

        # Simulate pipeline failure
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "failure"
        combined_status.total_count = 1

        status_fail = MagicMock()
        status_fail.state = "failure"
        status_fail.context = "ci/tests"
        status_fail.description = "Tests failed"
        combined_status.statuses = [status_fail]

        commit.get_combined_status.return_value = combined_status
        commit.get_check_runs.return_value = []
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        self.agent.ai_client.generate_pr_comment.return_value = "Please fix the pipeline issues."

        self.agent.process_pr(pr)

        # Verify that a comment was requested (asking for correction)
        self.agent.ai_client.generate_pr_comment.assert_called()
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
        pr.base.repo.full_name = "juninmd/repo"
        # Mock PR created 15 minutes ago (older than min age)
        from datetime import datetime, timezone, timedelta
        pr.created_at = datetime.now(timezone.utc) - timedelta(minutes=15)

        # Mock accept_review_suggestions
        self.mock_github.accept_review_suggestions.return_value = (True, "No suggestions", 0)

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
        (Or whatever is in allowed_authors)
        """
        pr = MagicMock()
        pr.number = 4
        pr.user.login = "other-developer"
        pr.mergeable = True
        pr.base.repo.full_name = "juninmd/repo"

        # Even if it is successful
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "success"
        commit.get_combined_status.return_value = combined_status
        commit.get_check_runs.return_value = []
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        result = self.agent.process_pr(pr)
        self.assertEqual(result["action"], "skipped")

        # Verify NO action
        self.mock_github.merge_pr.assert_not_called()
        pr.create_issue_comment.assert_not_called()

if __name__ == '__main__':
    unittest.main()
