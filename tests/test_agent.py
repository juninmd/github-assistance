import unittest
import subprocess
from unittest.mock import MagicMock, patch, call
from src.agents.pr_assistant.agent import PRAssistantAgent

class TestAgent(unittest.TestCase):
    def setUp(self):
        self.mock_github = MagicMock()
        self.mock_jules = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True
        self.agent = PRAssistantAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            allowed_authors=["juninmd"]
        )
        # Mock AI client to enable autonomous features in tests
        self.agent.ai_client = MagicMock()

    def test_run_flow(self):
        # Mock search result
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.repository.full_name = "juninmd/test-repo"
        mock_issue.title = "Test PR"

        mock_pr = MagicMock()
        mock_pr.number = 1
        mock_pr.user.login = "juninmd"
        mock_pr.title = "Test PR"
        mock_pr.html_url = "https://github.com/repo/pull/1"
        mock_pr.draft = False  # Ensure it's not draft

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
            self.assertIn("*Pulados/Pendentes:* 1", summary_call)

    def test_process_pr_clean_merge(self):
        pr = MagicMock()
        pr.number = 1
        pr.mergeable = True
        pr.user.login = "juninmd"

        # Mock commits and status
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "success"
        commit.get_combined_status.return_value = combined_status
        commit.get_check_runs.return_value = []
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        self.mock_github.merge_pr.return_value = (True, "Merged")
        self.agent.process_pr(pr)

        self.mock_github.merge_pr.assert_called_with(pr)
        self.mock_github.send_telegram_notification.assert_called_with(pr)

    def test_process_pr_pipeline_pending(self):
        pr = MagicMock()
        pr.number = 4
        pr.mergeable = True
        pr.user.login = "juninmd"

        # Mock commits and status
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "pending"
        combined_status.total_count = 1
        commit.get_combined_status.return_value = combined_status
        commit.get_check_runs.return_value = []
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
        pr.user.login = "juninmd"

        # Mock 0 commits
        pr.get_commits.return_value.totalCount = 0

        self.agent.process_pr(pr)

        # Should NOT merge because pipeline_success is False
        self.mock_github.merge_pr.assert_not_called()

    def test_process_pr_pipeline_unknown_state(self):
        pr = MagicMock()
        pr.number = 11
        pr.mergeable = True
        pr.user.login = "juninmd"

        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "unknown_state"
        combined_status.total_count = 1
        commit.get_combined_status.return_value = combined_status
        commit.get_check_runs.return_value = []
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        self.agent.process_pr(pr)

        # Should NOT merge because state is not success
        self.mock_github.merge_pr.assert_not_called()

    def test_process_pr_pipeline_failure(self):
        # Disable AI client for this test to check fallback template
        self.agent.ai_client = None

        pr = MagicMock()
        pr.number = 2
        pr.mergeable = True
        pr.user.login = "juninmd"

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

        self.agent.process_pr(pr)

        # Verify that a comment was created with the expected failure description
        pr.create_issue_comment.assert_called_once()
        comment_text = pr.create_issue_comment.call_args[0][0]

        # Check that the comment contains expected elements from the template
        self.assertIn("❌ **Pipeline Failure Detected**", comment_text)
        self.assertIn("@juninmd", comment_text)
        self.assertIn("Pipeline failed with status:", comment_text)
        self.assertIn("ci/build: Build failed", comment_text)

        self.mock_github.merge_pr.assert_not_called()

    @patch("src.agents.pr_assistant.agent.subprocess")
    def test_handle_conflicts_logic(self, mock_subprocess):
        # Refined test for conflicts
        pr = MagicMock()
        pr.number = 3
        pr.mergeable = False
        pr.user.login = "juninmd"
        # We need to simulate allowlist check passing
        self.agent.allowed_authors = ["juninmd"]

        # Mocking resolve_conflicts_autonomously to verify call
        with patch.object(self.agent, 'resolve_conflicts_autonomously') as mock_resolve:
            self.agent.process_pr(pr)
            mock_resolve.assert_called_once_with(pr)

    def test_process_pr_wrong_author(self):
        pr = MagicMock()
        pr.number = 9
        pr.user.login = "other-user"

        result = self.agent.process_pr(pr)
        self.assertEqual(result["action"], "skipped")
        self.assertEqual(result["reason"], "unauthorized_author")

        # Should do nothing
        self.mock_github.merge_pr.assert_not_called()

    def test_process_pr_mergeable_none(self):
        pr = MagicMock()
        pr.number = 99
        pr.user.login = "juninmd"
        pr.mergeable = None

        with patch("builtins.print") as mock_print:
            self.agent.process_pr(pr)
            mock_print.assert_any_call("[pr_assistant] [INFO] PR #99 mergeability unknown")

    def test_run_with_draft_prs(self):
        """Test that draft PRs are tracked and included in summary"""
        # Mock search result with draft and non-draft PRs
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

        # Mock issues object
        mock_issues = MagicMock()
        mock_issues.totalCount = 2
        mock_issues.__iter__.return_value = iter([mock_issue_draft, mock_issue_ready])

        self.mock_github.search_prs.return_value = mock_issues
        self.mock_github.get_pr_from_issue.side_effect = [mock_pr_draft, mock_pr_ready]

        # Mock process_pr for the ready PR
        with patch.object(self.agent, 'process_pr', return_value={"action": "skipped", "pr": 2}):
            result = self.agent.run()

            # Verify draft PR is tracked
            self.assertEqual(len(result['draft_prs']), 1)
            self.assertEqual(result['draft_prs'][0]['pr'], 1)
            self.assertEqual(result['draft_prs'][0]['title'], "Draft PR")
            self.assertEqual(result['draft_prs'][0]['url'], "https://github.com/juninmd/test-repo/pull/1")

            # Verify telegram summary includes draft count and links
            summary_call = self.mock_github.send_telegram_msg.call_args[0][0]
            self.assertIn("Draft:", summary_call)
            self.assertIn("*PRs em Draft:*", summary_call)
            self.assertIn("test\\-repo#1", summary_call)
            # Verify ready PR was processed
            self.assertIn("*Pulados/Pendentes:*", summary_call)

        # Should NOT merge, should NOT comment
        self.mock_github.merge_pr.assert_not_called()
        mock_pr_draft.create_issue_comment.assert_not_called()

    @patch("src.agents.pr_assistant.agent.subprocess")
    @patch("src.agents.pr_assistant.agent.tempfile.TemporaryDirectory")
    def test_handle_conflicts_subprocess_calls(self, mock_temp_dir, mock_subprocess):
        # Setup PR data for a fork scenario
        pr = MagicMock()
        pr.number = 5
        pr.user.login = "juninmd"  # Trusted author
        pr.base.repo.full_name = "juninmd/repo"
        pr.head.repo.full_name = "fork-user/repo"
        pr.base.repo.clone_url = "https://github.com/juninmd/repo.git"
        pr.head.repo.clone_url = "https://github.com/fork-user/repo.git"
        pr.head.ref = "feature-branch"
        pr.base.ref = "main"

        # Ensure ids are different to simulate fork
        pr.head.repo.id = 100
        pr.base.repo.id = 200

        # Mock token
        self.agent.github_client.token = "TEST_TOKEN"

        # Mock temp dir
        mock_temp_dir.return_value.__enter__.return_value = "/tmp/mock_repo_dir"

        work_dir = "/tmp/mock_repo_dir/repo"

        # Mock subprocess to simulate clean merge
        mock_subprocess.run.return_value.returncode = 0

        self.agent.handle_conflicts(pr)

        # Expected URL with token
        expected_head_url = "https://x-access-token:TEST_TOKEN@github.com/fork-user/repo.git"
        expected_base_url = "https://x-access-token:TEST_TOKEN@github.com/juninmd/repo.git"

        # Verify Clone (Head)
        mock_subprocess.run.assert_any_call(
            ["git", "clone", expected_head_url, work_dir],
            check=True, capture_output=True
        )

        # Verify Config
        mock_subprocess.run.assert_any_call(
            ["git", "config", "user.email", "agent@juninmd.com"], cwd=work_dir, check=True
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
            cwd=work_dir, capture_output=True, text=True
        )

    @patch("src.agents.pr_assistant.agent.subprocess")
    @patch("src.agents.pr_assistant.agent.tempfile.TemporaryDirectory")
    def test_handle_conflicts_merge_success_push_fail(self, mock_temp_dir, mock_subprocess):
        pr = MagicMock()
        pr.number = 8
        pr.user.login = "juninmd"  # Trusted author
        pr.base.repo.full_name = "juninmd/repo"
        pr.head.repo.full_name = "fork-user/repo"
        pr.base.repo.clone_url = "https://github.com/juninmd/repo.git"
        pr.head.repo.clone_url = "https://github.com/fork-user/repo.git"
        pr.head.ref = "feature-branch"
        pr.base.ref = "main"

        # Fork scenario
        pr.head.repo.id = 100
        pr.base.repo.id = 200

        self.agent.github_client.token = "TEST_TOKEN"
        mock_temp_dir.return_value.__enter__.return_value = "/tmp/mock_repo_dir"

        # Simulate merge success but push failure
        def side_effect(cmd, **kwargs):
            if cmd[1] == "push":
                raise subprocess.CalledProcessError(1, cmd, stderr=b"Push failed")
            # For merge command, return success object
            if cmd[1] == "merge":
                mock_res = MagicMock()
                mock_res.returncode = 0
                return mock_res
            return MagicMock()

        mock_subprocess.run.side_effect = side_effect
        mock_subprocess.CalledProcessError = subprocess.CalledProcessError

        with patch("builtins.print") as mock_print:
            self.agent.handle_conflicts(pr)

            # Check for error log
            found_msg = False
            for call in mock_print.call_args_list:
                args, _ = call
                if "[pr_assistant] [ERROR] Git operation failed:" in args[0]:
                    found_msg = True
                    break
            self.assertTrue(found_msg, "Did not find expected error message for push failure")

        # Verify diff was NOT called (conflict resolution skipped because merge succeeded locally)
        mock_subprocess.check_output.assert_not_called()

    @patch("src.agents.pr_assistant.agent.subprocess")
    def test_handle_conflicts_missing_head_repo(self, mock_subprocess):
        pr = MagicMock()
        pr.number = 6
        pr.user.login = "juninmd"  # Trusted author
        pr.base.repo.full_name = "juninmd/repo"
        pr.head.repo = None  # Simulate deleted fork
        # If head.repo is None, accessing it raises AttributeError if not careful
        # Our code explicitly checks `if not pr.head or not pr.head.repo:`

        # But `pr.head` is a MagicMock usually.
        # If we set `pr.head.repo = None`, accessing `pr.head.repo` returns None.

        # We also need to set pr.head to something valid but with repo=None?
        # MagicMock creates attributes on access.
        # `pr.head` is a Mock. `pr.head.repo` is a Mock.
        # So we explicitly set `pr.head.repo = None`.

        # Wait, if `pr.head.repo` is None, accessing `pr.head.repo.full_name` would raise AttributeError.
        # So we test that our code avoids this access.

        with patch("builtins.print") as mock_print:
            self.agent.handle_conflicts(pr)
            # Expecting warning
            mock_print.assert_any_call("[pr_assistant] [WARNING] PR #6 head repository is missing (deleted fork?)")

        # Ensure no subprocess commands were run (no cloning)
        mock_subprocess.run.assert_not_called()

    def test_handle_pipeline_failure_duplicate_comment(self):
        pr = MagicMock()
        pr.number = 7
        pr.mergeable = True
        pr.user.login = "juninmd"

        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "failure"
        combined_status.total_count = 1

        status_fail = MagicMock()
        status_fail.state = "failure"
        status_fail.context = "ci/build"
        status_fail.description = "Build failed"
        combined_status.statuses = [status_fail]

        commit.get_combined_status.return_value = combined_status
        commit.get_check_runs.return_value = []
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        # Mock existing comments with new failure message format
        mock_comment = MagicMock()
        mock_comment.body = "❌ Pipeline Failure Detected\n\nHi @juninmd, the CI/CD pipeline for this PR has failed."
        self.mock_github.get_issue_comments.return_value = [mock_comment]

        self.agent.process_pr(pr)

        self.mock_github.get_issue_comments.assert_called_with(pr)
        # Should NOT comment again
        pr.create_issue_comment.assert_not_called()
        self.mock_github.merge_pr.assert_not_called()

    def test_process_pr_pipeline_neutral(self):
        pr = MagicMock()
        pr.number = 12
        pr.mergeable = True
        pr.user.login = "juninmd"

        # Mock commits and status as neutral
        commit = MagicMock()
        combined_status = MagicMock()
        combined_status.state = "neutral"
        combined_status.total_count = 1
        commit.get_combined_status.return_value = combined_status

        # Also mock CheckRun as neutral
        check_run = MagicMock()
        check_run.status = "completed"
        check_run.conclusion = "neutral"
        commit.get_check_runs.return_value = [check_run]

        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        self.mock_github.merge_pr.return_value = (True, "Merged")
        self.agent.process_pr(pr)

        # Should merge because neutral is success
        self.mock_github.merge_pr.assert_called_with(pr)

    @patch("src.agents.pr_assistant.agent.subprocess")
    @patch("src.agents.pr_assistant.agent.tempfile.TemporaryDirectory")
    def test_handle_conflicts_token_redaction(self, mock_temp_dir, mock_subprocess):
        pr = MagicMock()
        pr.number = 9
        pr.user.login = "juninmd"
        pr.base.repo.full_name = "juninmd/repo"
        pr.head.repo.full_name = "fork-user/repo"
        pr.base.repo.clone_url = "https://github.com/juninmd/repo.git"
        pr.head.repo.clone_url = "https://github.com/fork-user/repo.git"
        pr.head.ref = "feature-branch"
        pr.base.ref = "main"

        pr.head.repo.id = 100
        pr.base.repo.id = 200

        token = "SECRET_TOKEN_123"
        self.agent.github_client.token = token
        mock_temp_dir.return_value.__enter__.return_value = "/tmp/mock_repo_dir"

        # Simulate clone failure with token in command
        cmd = ["git", "clone", f"https://x-access-token:{token}@github.com/fork-user/repo.git", "/tmp/mock_repo_dir/repo"]
        error = subprocess.CalledProcessError(1, cmd, stderr=f"fatal: unable to access 'https://x-access-token:{token}@github.com/fork-user/repo.git': The requested URL returned error: 403".encode('utf-8'))
        mock_subprocess.run.side_effect = error
        mock_subprocess.CalledProcessError = subprocess.CalledProcessError

        with patch("builtins.print") as mock_print:
            self.agent.handle_conflicts(pr)

            # Verify no log contains the token
            for call in mock_print.call_args_list:
                args, _ = call
                log_msg = args[0]
                self.assertNotIn(token, log_msg, f"Token found in log: {log_msg}")
                if "Git operation failed" in log_msg:
                    self.assertIn("[REDACTED]", log_msg)
                if "Stderr" in log_msg:
                    self.assertIn("[REDACTED]", log_msg)

if __name__ == '__main__':
    unittest.main()
