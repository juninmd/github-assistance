import os
import subprocess
import unittest
from datetime import UTC
from unittest.mock import ANY, MagicMock, call, patch

from src.agents.pr_assistant.agent import PRAssistantAgent


class TestAgent(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True

        # Patch get_ai_client to avoid initialization issues
        self.patcher = patch("src.agents.pr_assistant.agent.get_ai_client")
        self.mock_get_client = self.patcher.start()

        # Setup mock AI client
        self.mock_ai_client = MagicMock()
        self.mock_get_client.return_value = self.mock_ai_client

        self.agent = PRAssistantAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            allowed_authors=["juninmd"],
            target_owner="juninmd"
        )

    def tearDown(self):
        self.patcher.stop()

    def test_init_options(self):
        # Reset mock call
        self.mock_get_client.reset_mock()

        PRAssistantAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            target_owner="juninmd",
            ai_provider="ollama",
            ai_model="llama3",
            ai_config={"base_url": "http://test"}
        )
        self.mock_get_client.assert_called_with("ollama", base_url="http://test", model="llama3")

    def test_run_flow(self):
        # Mock search result
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.repository.full_name = "juninmd/test-repo"
        mock_issue.title = "Test PR"

        mock_pr = MagicMock()
        mock_pr.number = 1
        mock_pr.draft = False
        mock_pr.user.login = "juninmd"
        mock_pr.title = "Test PR"
        mock_pr.html_url = "https://github.com/repo/pull/1"

        # Mock issues object with totalCount
        mock_issues = MagicMock()
        mock_issues.totalCount = 1
        mock_issues.__iter__.return_value = iter([mock_issue])
        self.mock_github.search_prs.return_value = mock_issues
        self.mock_github.get_pr_from_issue.return_value = mock_pr

        # Mock process_pr calls
        with patch.object(self.agent, 'process_pr', return_value={"action": "skipped", "pr": 1}) as mock_process:
            self.agent.run()

            self.mock_github.search_prs.assert_called()
            self.mock_github.get_pr_from_issue.assert_called()
            mock_process.assert_called()

            # Verify final summary call
            self.mock_github.send_telegram_msg.assert_called()
            summary_call = self.mock_github.send_telegram_msg.call_args[0][0]
            self.assertIn("PR Assistant Summary", summary_call)
            self.assertIn("*Total Analisados:* 1", summary_call)

    def test_process_pr_clean_merge(self):
        pr = MagicMock()
        pr.number = 1
        pr.mergeable = True
        pr.user.login = "juninmd"
        pr.base.repo.full_name = "juninmd/test-repo"
        # Mock PR created 15 minutes ago (older than min age)
        from datetime import datetime, timedelta, timezone
        pr.created_at = datetime.now(UTC) - timedelta(minutes=15)

        # Mock commits and status
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "success"
        commit.get_combined_status.return_value = combined_status
        commit.get_check_runs.return_value = []
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        # Mock accept_review_suggestions
        self.mock_github.accept_review_suggestions.return_value = (True, "No suggestions", 0)

        self.mock_github.merge_pr.return_value = (True, "Merged")
        self.agent.process_pr(pr)

        self.mock_github.merge_pr.assert_called_with(pr)
        self.mock_github.add_label_to_pr.assert_called_with(pr, "auto-merge")
        self.mock_github.comment_on_pr.assert_called_with(pr, "✅ Este PR foi mergeado automaticamente pelo PR Assistant.")
        self.mock_github.send_telegram_notification.assert_called_with(pr)

    def test_process_pr_pipeline_failure(self):
        pr = MagicMock()
        pr.number = 2
        pr.mergeable = True
        pr.user.login = "juninmd"
        pr.base.repo.full_name = "juninmd/test-repo"
        # Mock PR created 15 minutes ago (older than min age)
        from datetime import datetime, timedelta, timezone
        pr.created_at = datetime.now(UTC) - timedelta(minutes=15)

        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "failure"

        # Mock failed status
        status_fail = MagicMock()
        status_fail.state = "failure"
        status_fail.context = "ci/build"
        status_fail.description = "Build failed"

        combined_status.statuses = [status_fail]
        combined_status.total_count = 1

        commit.get_combined_status.return_value = combined_status
        commit.get_check_runs.return_value = []
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        # Mock accept_review_suggestions
        self.mock_github.accept_review_suggestions.return_value = (True, "No suggestions", 0)

        # Mock AI generation
        self.agent.ai_client.generate_pr_comment.return_value = "AI generated comment"

        self.agent.process_pr(pr)

        # Verify that a comment was created
        pr.create_issue_comment.assert_called_once_with("AI generated comment")
        self.mock_github.merge_pr.assert_not_called()

    @patch("src.agents.pr_assistant.agent.subprocess")
    @patch("src.agents.pr_assistant.agent.tempfile.TemporaryDirectory")
    def test_resolve_conflicts_autonomously_flow(self, mock_tempdir, mock_subprocess):
        # Verify complete autonomous flow
        pr = MagicMock()
        pr.number = 3
        pr.mergeable = False
        pr.user.login = "juninmd"
        pr.base.repo.full_name = "juninmd/repo"
        pr.head.repo.full_name = "fork-user/repo"
        pr.base.repo.clone_url = "https://github.com/juninmd/repo.git"
        pr.head.repo.clone_url = "https://github.com/fork-user/repo.git"
        pr.head.ref = "feature"
        pr.base.ref = "main"
        pr.head.repo.id = 1
        pr.base.repo.id = 2 # Different ID = fork
        # Mock PR created 15 minutes ago (older than min age)
        from datetime import datetime, timedelta, timezone
        pr.created_at = datetime.now(UTC) - timedelta(minutes=15)

        self.agent.github_client.token = "TOKEN"

        # Mock accept_review_suggestions
        self.mock_github.accept_review_suggestions.return_value = (True, "No suggestions", 0)

        # Setup temp dir
        mock_tempdir.return_value.__enter__.return_value = "/tmp/repo"

        # Setup subprocess responses
        # git merge returns non-zero (conflict)
        # git diff returns list of files
        # git commit, push return success

        def subprocess_run_side_effect(cmd, **kwargs):
            mock_res = MagicMock()
            mock_res.returncode = 0
            if cmd[1] == "merge":
                if kwargs.get("check"):
                    raise subprocess.CalledProcessError(1, cmd)
                mock_res.returncode = 1 # Conflict
            return mock_res

        mock_subprocess.CalledProcessError = subprocess.CalledProcessError
        mock_subprocess.run.side_effect = subprocess_run_side_effect
        mock_subprocess.check_output.return_value = b"file1.py\n"

        # Mock file operations
        with patch("builtins.open", unittest.mock.mock_open(read_data="<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> feature\n")):
             self.agent.ai_client.resolve_conflict.return_value = "resolved\n"

             self.agent.process_pr(pr)

             # Verify sequence
             # 1. Clone
             mock_subprocess.run.assert_any_call(["git", "clone", ANY, "/tmp/repo/repo"], check=True, capture_output=True)
             # 2. Config
             # 3. Checkout
             # 4. Remote add (fork)
             # Note: Implementation might clone HEAD or BASE. Our implementation clones HEAD.
             # So we expect 'upstream' to be added.
             mock_subprocess.run.assert_any_call(["git", "remote", "add", "upstream", ANY], cwd="/tmp/repo/repo", check=True)
             # 5. Merge
             # 6. Resolve (AI called)
             self.agent.ai_client.resolve_conflict.assert_called()
             # 7. Commit
             mock_subprocess.run.assert_any_call(["git", "commit", "-m", ANY], cwd="/tmp/repo/repo", check=True)
             # 8. Push
             mock_subprocess.run.assert_any_call(["git", "push", "origin", "feature"], cwd="/tmp/repo/repo", check=True)

    def test_process_pr_mergeable_none(self):
        # We need to test the logging output here
        pr = MagicMock()
        pr.number = 99
        pr.user.login = "juninmd"
        pr.mergeable = None
        pr.base.repo.full_name = "juninmd/repo"
        # Mock PR created 15 minutes ago (older than min age)
        from datetime import datetime, timedelta, timezone
        pr.created_at = datetime.now(UTC) - timedelta(minutes=15)

        # Mock accept_review_suggestions
        self.mock_github.accept_review_suggestions.return_value = (True, "No suggestions", 0)

        # Patch log method or print
        with patch.object(self.agent, 'log') as mock_log:
            result = self.agent.process_pr(pr)
            mock_log.assert_any_call("PR #99 mergeability unknown")
            self.assertEqual(result["action"], "skipped")

    def test_run_with_draft_prs(self):
        """Test that draft PRs are tracked and included in summary"""
        mock_issue_draft = MagicMock()
        mock_issue_draft.number = 1
        mock_issue_draft.repository.full_name = "juninmd/test-repo"
        mock_issue_draft.title = "Draft PR"

        mock_issue_ready = MagicMock()
        mock_issue_ready.number = 2
        mock_issue_ready.repository.full_name = "juninmd/test-repo"
        mock_issue_ready.title = "Ready PR"

        mock_pr_draft = MagicMock()
        mock_pr_draft.number = 1
        mock_pr_draft.draft = True
        mock_pr_draft.user.login = "juninmd"
        mock_pr_draft.title = "Draft PR"
        mock_pr_draft.html_url = "https://github.com/juninmd/test-repo/pull/1"

        mock_pr_ready = MagicMock()
        mock_pr_ready.number = 2
        mock_pr_ready.draft = False
        mock_pr_ready.user.login = "juninmd"
        mock_pr_ready.title = "Ready PR"
        mock_pr_ready.mergeable = True

        # Setup mock ready PR commit status
        commit = MagicMock()
        commit.get_combined_status.return_value.state = "success"
        commit.get_check_runs.return_value = []
        mock_pr_ready.get_commits.return_value.reversed = [commit]
        mock_pr_ready.get_commits.return_value.totalCount = 1

        mock_issues = MagicMock()
        mock_issues.totalCount = 2
        mock_issues.__iter__.return_value = iter([mock_issue_draft, mock_issue_ready])

        self.mock_github.search_prs.return_value = mock_issues
        self.mock_github.get_pr_from_issue.side_effect = [mock_pr_draft, mock_pr_ready]
        self.mock_github.merge_pr.return_value = (True, "Merged")

        result = self.agent.run()

        # Verify draft PR is tracked
        self.assertEqual(len(result['draft_prs']), 1)

        # Verify telegram summary
        summary_call = self.mock_github.send_telegram_msg.call_args[0][0]
        self.assertIn("Draft:", summary_call)
        self.assertIn("*PRs em Draft:*", summary_call)
        self.assertIn(r"test\-repo\#1", summary_call) # Escaped

if __name__ == '__main__':
    unittest.main()
