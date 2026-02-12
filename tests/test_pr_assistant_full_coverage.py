import unittest
from unittest.mock import MagicMock, patch, call, mock_open
from src.agents.pr_assistant.agent import PRAssistantAgent

class TestPRAssistantFullCoverage(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.mock_allowlist.is_allowed.return_value = True

        # Patch get_ai_client to avoid actual AI client creation
        self.patcher = patch("src.agents.pr_assistant.agent.get_ai_client")
        self.mock_get_ai = self.patcher.start()
        self.mock_ai_client = MagicMock()
        self.mock_get_ai.return_value = self.mock_ai_client

        self.agent = PRAssistantAgent(
            self.mock_jules,
            self.mock_github,
            self.mock_allowlist,
            target_owner="juninmd"
        )

    def tearDown(self):
        self.patcher.stop()

    def test_pipeline_status_billing_error(self):
        """Test detection of billing/limit errors."""
        pr = MagicMock()
        commit = MagicMock()
        combined = MagicMock()
        combined.state = "failure"
        combined.total_count = 1

        status = MagicMock()
        status.state = "failure"
        status.description = "account payments disabled"
        status.context = "ci/billing"

        combined.statuses = [status]
        commit.get_combined_status.return_value = combined
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        result = self.agent.check_pipeline_status(pr)
        self.assertFalse(result["success"])
        self.assertIn("billing/limit", result["details"])

    def test_pipeline_status_other_failures(self):
        """Test detection of generic status failures."""
        pr = MagicMock()
        commit = MagicMock()
        combined = MagicMock()
        combined.state = "failure"
        combined.total_count = 1

        status = MagicMock()
        status.state = "failure"
        status.description = "tests failed"
        status.context = "ci/tests"

        combined.statuses = [status]
        commit.get_combined_status.return_value = combined
        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        result = self.agent.check_pipeline_status(pr)
        self.assertFalse(result["success"])
        self.assertIn("tests failed", result["details"])

    def test_pipeline_status_check_runs_pending(self):
        """Test detection of pending check runs."""
        pr = MagicMock()
        commit = MagicMock()
        commit.get_combined_status.return_value.state = "success"

        run = MagicMock()
        run.status = "queued"
        run.name = "build"
        commit.get_check_runs.return_value = [run]

        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        result = self.agent.check_pipeline_status(pr)
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "pending")

    def test_pipeline_status_check_runs_failure(self):
        """Test detection of failed check runs."""
        pr = MagicMock()
        commit = MagicMock()
        commit.get_combined_status.return_value.state = "success"

        run = MagicMock()
        run.status = "completed"
        run.conclusion = "failure"
        run.name = "lint"
        commit.get_check_runs.return_value = [run]

        pr.get_commits.return_value.reversed = [commit]
        pr.get_commits.return_value.totalCount = 1

        result = self.agent.check_pipeline_status(pr)
        self.assertFalse(result["success"])
        self.assertIn("lint: failure", result["details"])

    def test_pipeline_status_exception(self):
        """Test exception handling in check_pipeline_status."""
        pr = MagicMock()
        pr.get_commits.side_effect = Exception("API Error")

        result = self.agent.check_pipeline_status(pr)
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "error")

    def test_process_pr_draft(self):
        """Test skipping of draft PRs in run loop (simulated via manual check as run loop is complex)."""
        # Note: The 'draft' check is inside run(), not process_pr().
        # process_pr assumes the PR is valid to be processed.
        # So we test run() directly for this.
        pass # See test_run_draft_pr

    def test_run_draft_pr(self):
        """Test that run loop identifies and skips draft PRs."""
        pr = MagicMock()
        pr.draft = True
        pr.number = 101
        pr.title = "Draft PR"
        pr.user.login = "juninmd"
        pr.html_url = "http://github.com/owner/repo/pull/101"

        issue = MagicMock()
        issue.number = 101
        issue.repository.full_name = "owner/repo"

        mock_list = MagicMock()
        mock_list.__iter__.return_value = [issue]
        mock_list.totalCount = 1
        self.mock_github.search_prs.return_value = mock_list

        self.mock_github.get_pr_from_issue.return_value = pr

        results = self.agent.run()

        self.assertEqual(len(results["draft_prs"]), 1)
        self.assertEqual(results["draft_prs"][0]["pr"], 101)

    def test_run_results_categorization(self):
        """Test that run loop categorizes results correctly."""
        pr_merged = MagicMock()
        pr_merged.draft = False
        pr_merged.number = 1
        pr_merged.user.login = "juninmd"

        pr_conflict = MagicMock()
        pr_conflict.draft = False
        pr_conflict.number = 2
        pr_conflict.user.login = "juninmd"

        pr_pipeline = MagicMock()
        pr_pipeline.draft = False
        pr_pipeline.number = 3
        pr_pipeline.user.login = "juninmd"

        pr_skipped = MagicMock()
        pr_skipped.draft = False
        pr_skipped.number = 4
        pr_skipped.user.login = "other" # unauthorized

        # Mock search results
        issue1 = MagicMock(); issue1.number = 1; issue1.repository.full_name = "repo/1"
        issue2 = MagicMock(); issue2.number = 2; issue2.repository.full_name = "repo/1"
        issue3 = MagicMock(); issue3.number = 3; issue3.repository.full_name = "repo/1"
        issue4 = MagicMock(); issue4.number = 4; issue4.repository.full_name = "repo/1"

        mock_list = MagicMock()
        mock_list.__iter__.return_value = [issue1, issue2, issue3, issue4]
        mock_list.totalCount = 4
        self.mock_github.search_prs.return_value = mock_list

        # Mock get_pr_from_issue to return corresponding PRs
        self.mock_github.get_pr_from_issue.side_effect = [pr_merged, pr_conflict, pr_pipeline, pr_skipped]

        # Mock process_pr results
        with patch.object(self.agent, 'process_pr') as mock_process:
            mock_process.side_effect = [
                {"action": "merged", "pr": 1},
                {"action": "conflicts_resolved", "pr": 2},
                {"action": "pipeline_failure", "pr": 3},
                {"action": "skipped", "pr": 4}
            ]

            results = self.agent.run()

            self.assertEqual(len(results["merged"]), 1)
            self.assertEqual(len(results["conflicts_resolved"]), 1)
            self.assertEqual(len(results["pipeline_failures"]), 1)
            self.assertEqual(len(results["skipped"]), 1)

    def test_run_exception_handling(self):
        """Test exception handling in run loop."""
        issue = MagicMock()
        issue.number = 99
        issue.repository.full_name = "owner/repo"
        issue.title = "Issue Title"
        issue.html_url = "http://url"

        mock_list = MagicMock()
        mock_list.__iter__.return_value = [issue]
        mock_list.totalCount = 1
        self.mock_github.search_prs.return_value = mock_list

        self.mock_github.get_pr_from_issue.side_effect = Exception("Network Error")

        results = self.agent.run()
        self.assertEqual(len(results["skipped"]), 1)
        self.assertIn("Network Error", results["skipped"][0]["error"])

    def test_run_search_exception(self):
        """Test exception during PR search."""
        self.mock_github.search_prs.side_effect = Exception("API Down")
        results = self.agent.run()
        self.assertEqual(results["status"], "error")

    def test_telegram_summary_escaping(self):
        """Test that telegram summary generation handles special chars."""
        # Setup a run with results that have special chars
        pr = MagicMock()
        pr.draft = False
        pr.number = 1
        pr.title = "Fix: [Bug] *Important*"
        pr.user.login = "juninmd"

        issue = MagicMock()
        issue.repository.full_name = "owner/repo_name"

        mock_list = MagicMock()
        mock_list.__iter__.return_value = [issue]
        mock_list.totalCount = 1
        self.mock_github.search_prs.return_value = mock_list

        self.mock_github.get_pr_from_issue.return_value = pr

        with patch.object(self.agent, 'process_pr') as mock_process:
            mock_process.return_value = {"action": "merged", "pr": 1, "title": "Fix: [Bug] *Important*", "url": "http://url"}

            results = self.agent.run()

            # Check arguments passed to send_telegram_msg
            self.mock_github.send_telegram_msg.assert_called_once()
            msg = self.mock_github.send_telegram_msg.call_args[0][0]

            # Verify escaping
            self.assertIn("repo\\_name", msg)
            self.assertIn("\\[Bug\\]", msg)
            self.assertIn("\\*Important\\*", msg)

    def test_resolve_conflicts_autonomously_exception(self):
        """Test exception handling in autonomous resolution."""
        pr = MagicMock()
        pr.base.repo.clone_url = "https://github.com/base/repo"
        pr.head.repo.clone_url = "https://github.com/head/repo"

        with patch("subprocess.run", side_effect=Exception("Git Error")):
             success = self.agent.resolve_conflicts_autonomously(pr)
             self.assertFalse(success)

    def test_notify_conflicts_exception(self):
        """Test exception handling in notify_conflicts."""
        pr = MagicMock()
        # Mock get_issue_comments to raise exception
        self.mock_github.get_issue_comments.side_effect = Exception("API Error")

        self.agent.notify_conflicts(pr)
        # Should catch exception and proceed to create comment
        pr.create_issue_comment.assert_called()

    def test_handle_pipeline_failure_ai_exception(self):
        """Test fallback when AI comment generation fails."""
        pr = MagicMock()
        pr.user.login = "juninmd"
        self.mock_github.get_issue_comments.return_value = []

        self.agent.ai_client.generate_pr_comment.side_effect = Exception("AI Error")

        self.agent.handle_pipeline_failure(pr, "Failure details")

        # Should call create_issue_comment with fallback text
        pr.create_issue_comment.assert_called()
        args = pr.create_issue_comment.call_args[0]
        self.assertIn("Pipeline Failure Detected", args[0])

    def test_run_summary_skipped_formatting(self):
        """Test formatting of skipped items without URL."""
        issue = MagicMock()
        issue.number = 1
        issue.title = "Skipped PR"
        issue.html_url = "http://url"
        issue.repository.full_name = "repo/1"

        mock_list = MagicMock()
        mock_list.__iter__.return_value = [issue]
        mock_list.totalCount = 1
        self.mock_github.search_prs.return_value = mock_list

        # Make get_pr_from_issue raise exception so it goes to skipped list via exception handler
        self.mock_github.get_pr_from_issue.side_effect = Exception("Fail")

        results = self.agent.run()

        self.mock_github.send_telegram_msg.assert_called()
        msg = self.mock_github.send_telegram_msg.call_args[0][0]
        self.assertIn("Pulados/Pendentes", msg)

    def test_summary_truncation(self):
        """Test that lists in summary are truncated if too long."""
        # Create 15 merged results
        issues = []
        count = 15 * 5 # 15 for each category
        for i in range(count):
            issue = MagicMock()
            issue.number = i
            issue.repository.full_name = "repo/1"
            issues.append(issue)

        mock_list = MagicMock()
        mock_list.__iter__.return_value = issues
        mock_list.totalCount = count
        self.mock_github.search_prs.return_value = mock_list

        # Mock PRs
        prs = [MagicMock(draft=False, number=i, title=f"PR {i}", user=MagicMock(login="juninmd"), html_url="url") for i in range(count)]

        # Set some as draft for the draft category logic which checks pr.draft before process_pr
        # The logic is: get_pr -> if pr.draft -> draft_prs.append -> continue
        # So we need to set pr.draft=True for the draft batch
        # Let's say indices 45-59 are drafts
        for i in range(45, 60):
            prs[i].draft = True

        self.mock_github.get_pr_from_issue.side_effect = prs

        # Mock process_pr results
        # 0-14: merged
        # 15-29: conflicts_resolved
        # 30-44: pipeline_failures
        # 45-59: skipped (but these are drafts so process_pr won't be called for them)
        # 60-74: skipped (explicit)

        side_effects = []
        for i in range(15): side_effects.append({"action": "merged", "pr": i, "title": f"PR {i}", "url": "url"})
        for i in range(15, 30): side_effects.append({"action": "conflicts_resolved", "pr": i, "title": f"PR {i}", "url": "url"})
        for i in range(30, 45): side_effects.append({"action": "pipeline_failure", "pr": i, "title": f"PR {i}", "url": "url"})
        # 45-59 are drafts, so process_pr not called
        for i in range(60, 75): side_effects.append({"action": "skipped", "pr": i, "title": f"PR {i}", "reason": "skip", "url": "url"})

        with patch.object(self.agent, 'process_pr') as mock_process:
            mock_process.side_effect = side_effects

            self.agent.run()

            msg = self.mock_github.send_telegram_msg.call_args[0][0]
            self.assertIn("e mais 5 PRs", msg) # merged
            self.assertIn("e mais 5 conflitos", msg) # conflicts
            self.assertIn("e mais 5 falhas", msg) # pipeline
            self.assertIn("e mais 5 drafts", msg) # drafts
            self.assertIn("e mais 5 pulados", msg) # skipped

    def test_resolve_conflict_binary_file(self):
        """Test skipping binary files in conflict resolution."""
        pr = MagicMock()
        pr.base.repo.clone_url = "https://github.com/base/repo"
        pr.head.repo.clone_url = "https://github.com/head/repo"

        with patch("src.agents.pr_assistant.agent.tempfile.TemporaryDirectory") as mock_tmp:
            mock_tmp.return_value.__enter__.return_value = "/tmp/repo"
            with patch("subprocess.run"):
                # Mock diff output
                with patch("subprocess.check_output", return_value=b"binary.png\n"):
                    # Mock open to raise UnicodeDecodeError
                    with patch("builtins.open", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "")):
                        success = self.agent.resolve_conflicts_autonomously(pr)
                        # Should return True because it commits whatever it did (or didn't fail)
                        # In the code, it just continues loop, then commits.
                        # If no files added, git commit might fail, but let's assume subprocess.run doesn't raise
                        self.assertTrue(success)

    def test_resolve_conflict_no_markers(self):
        """Test handling files with no conflict markers."""
        pr = MagicMock()
        pr.base.repo.clone_url = "https://github.com/base/repo"
        pr.head.repo.clone_url = "https://github.com/head/repo"

        with patch("src.agents.pr_assistant.agent.tempfile.TemporaryDirectory") as mock_tmp:
            mock_tmp.return_value.__enter__.return_value = "/tmp/repo"
            with patch("subprocess.run"):
                with patch("subprocess.check_output", return_value=b"file.txt\n"):
                     # Mock open to return content without markers
                     with patch("builtins.open", mock_open(read_data="No markers here")):
                        success = self.agent.resolve_conflicts_autonomously(pr)
                        self.assertTrue(success)

if __name__ == '__main__':
    unittest.main()
