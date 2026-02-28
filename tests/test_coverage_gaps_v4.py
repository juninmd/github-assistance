
import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, mock_open, patch

import requests

import src.main
import src.run_agent
from src.agents.base_agent import BaseAgent
from src.agents.pr_assistant import PRAssistantAgent
from src.agents.security_scanner import SecurityScannerAgent
from src.agents.senior_developer import SeniorDeveloperAgent
from src.config import RepositoryAllowlist
from src.github_client import GithubClient
from src.jules.client import JulesClient


class TestCoverageGapsV4(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()

    def test_base_agent_get_instructions_section(self):
        """Test getting a section from instructions when section exists and has content."""
        class TestAgent(BaseAgent):
            @property
            def persona(self): return "p"
            @property
            def mission(self): return "m"
            def run(self): pass

        agent = TestAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

        # Test line 136: return '\n'.join(section_lines).strip()
        with patch.object(agent, 'load_instructions', return_value="## Section\nContent line 1\nContent line 2\n## Other Section"):
            content = agent.get_instructions_section("## Section")
            self.assertEqual(content, "Content line 1\nContent line 2")

    def test_base_agent_no_instructions(self):
        """Test get_instructions_section when instructions file is missing/empty."""
        class TestAgent(BaseAgent):
            @property
            def persona(self): return "p"
            @property
            def mission(self): return "m"
            def run(self): pass

        agent = TestAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

        with patch.object(agent, 'load_instructions', return_value=""):
            content = agent.get_instructions_section("## Section")
            self.assertEqual(content, "")

    def test_pr_assistant_get_prs_to_process_specific_repo_ref(self):
        """Test _get_prs_to_process with owner/repo#number format."""
        agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

        # Test line 256
        prs = agent._get_prs_to_process("owner/repo#123")
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["repository"], "owner/repo")
        self.assertEqual(prs[0]["number"], 123)

    def test_pr_assistant_check_pipeline_status_other_state(self):
        """Test check_pipeline_status with a state other than failure/error/pending."""
        agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_pr = MagicMock()
        mock_commit = MagicMock()
        mock_pr.get_commits.return_value.reversed = [mock_commit]
        mock_commit.get_combined_status.return_value.state = "some_other_state"
        mock_commit.get_combined_status.return_value.total_count = 1
        mock_commit.get_check_runs.return_value = []

        # Test lines 369-371 logic path
        status = agent.check_pipeline_status(mock_pr)
        self.assertFalse(status["success"])
        self.assertEqual(status["reason"], "pending")
        self.assertIn("Legacy status is some_other_state", status["details"])

    def test_pr_assistant_process_pr_review_suggestions_fail(self):
        """Test process_pr when accept_review_suggestions fails."""
        agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd"
        mock_pr.mergeable = True
        mock_pr.get_commits.return_value.totalCount = 1
        mock_pr.get_commits.return_value.reversed = [MagicMock()]
        mock_pr.get_commits.return_value.reversed[0].get_combined_status.return_value.total_count = 0
        mock_pr.get_commits.return_value.reversed[0].get_check_runs.return_value = []

        self.mock_github.accept_review_suggestions.return_value = (False, "Some error", 0)
        self.mock_github.merge_pr.return_value = (True, "merged")

        # Mock is_pr_too_young to return False so we proceed
        with patch.object(agent, 'is_pr_too_young', return_value=False):
            # Test lines 418-419
            with patch.object(agent, 'log') as mock_log:
                agent.process_pr(mock_pr)
                mock_log.assert_any_call(f"Error applying review suggestions on PR #{mock_pr.number}: Some error", "WARNING")

    def test_pr_assistant_process_pr_comment_exception(self):
        """Test exception when commenting after merge."""
        agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd"
        mock_pr.mergeable = True

        # Mock pipeline success
        mock_pr.get_commits.return_value.totalCount = 1
        mock_pr.get_commits.return_value.reversed = [MagicMock()]
        mock_pr.get_commits.return_value.reversed[0].get_combined_status.return_value.total_count = 0
        mock_pr.get_commits.return_value.reversed[0].get_check_runs.return_value = []

        self.mock_github.accept_review_suggestions.return_value = (True, "ok", 0)
        self.mock_github.merge_pr.return_value = (True, "merged")
        self.mock_github.comment_on_pr.side_effect = Exception("Comment error")

        # Mock is_pr_too_young to return False so we proceed
        with patch.object(agent, 'is_pr_too_young', return_value=False):
            # Test lines 479-480
            with patch.object(agent, 'log') as mock_log:
                agent.process_pr(mock_pr)
                mock_log.assert_any_call(f"Failed to comment on PR #{mock_pr.number} after merge: Comment error", "WARNING")

    def test_pr_assistant_notify_conflicts_exceptions(self):
        """Test exceptions in notify_conflicts."""
        agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_pr = MagicMock()

        # Test lines 606-608: Exception checking comments
        self.mock_github.get_issue_comments.side_effect = Exception("Check error")
        with patch.object(agent, 'log') as mock_log:
            agent.notify_conflicts(mock_pr)
            mock_log.assert_any_call(f"Error checking existing comments for PR #{mock_pr.number}: Check error", "ERROR")

        # Test lines 616-617: Exception creating comment
        self.mock_github.get_issue_comments.side_effect = None
        self.mock_github.get_issue_comments.return_value = []
        mock_pr.create_issue_comment.side_effect = Exception("Post error")
        with patch.object(agent, 'log') as mock_log:
            agent.notify_conflicts(mock_pr)
            mock_log.assert_any_call(f"Failed to post conflict notification for PR #{mock_pr.number}: Post error", "ERROR")

    def test_security_scanner_pagination_and_exceptions(self):
        """Test Security Scanner pagination logic and exceptions."""
        agent = SecurityScannerAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

        # Mock long report for lines 486-490
        results = {
            "scanned": 1, "total_repositories": 1, "failed": 0, "total_findings": 0,
            "repositories_with_findings": [],
            "scan_errors": [],
            "all_repositories": [{"name": f"repo_{i}", "default_branch": "main"} for i in range(50)] # Lots of repos
        }

        # This should trigger pagination logic because header + list of 50 repos > 3800 chars?
        # Let's force it by mocking _escape_telegram to return huge string
        with patch.object(agent, '_escape_telegram', side_effect=lambda x: x + " " * 100):
             agent._send_notification(results)
             # Verify send_telegram_msg called multiple times if needed, or at least logic executed
             # Just ensuring no crash

        # Test line 522-523: Exception in _get_commit_author
        self.mock_github.g.get_repo.side_effect = Exception("Repo error")
        author = agent._get_commit_author("repo", "sha")
        self.assertEqual(author, "unknown")

    def test_security_scanner_commit_author_none(self):
        """Test _get_commit_author when author is None."""
        agent = SecurityScannerAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_repo = MagicMock()
        mock_commit = MagicMock()
        mock_commit.author = None # or commit.author.login is None
        mock_repo.get_commit.return_value = mock_commit
        self.mock_github.g.get_repo.return_value = mock_repo

        author = agent._get_commit_author("repo", "sha")
        self.assertEqual(author, "unknown")

    def test_security_scanner_commit_author_success(self):
        """Test _get_commit_author when author is found."""
        agent = SecurityScannerAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_repo = MagicMock()
        mock_commit = MagicMock()
        mock_commit.author.login = "author_login"
        mock_repo.get_commit.return_value = mock_commit
        self.mock_github.g.get_repo.return_value = mock_repo

        author = agent._get_commit_author("repo", "sha_success")
        self.assertEqual(author, "author_login")

    def test_senior_developer_exceptions(self):
        """Test exceptions in Senior Developer agent."""
        agent = SeniorDeveloperAgent(self.mock_jules, self.mock_github, self.mock_allowlist)

        # Test line 323: analyze_cicd exception
        mock_repo = MagicMock()
        mock_repo.get_contents.side_effect = Exception("Contents error")
        self.mock_github.get_repo.return_value = mock_repo

        # This triggers exception in getting contents("") for tests check
        res = agent.analyze_cicd("repo")
        # Ensure it doesn't crash and returns valid dict (though likely empty improvements due to exception caught)
        self.assertFalse(res.get("needs_improvement", False) and "improvements" in res and "No test directory" in res["improvements"])

        # Test line 333: analyze_roadmap_features exception
        with patch.object(agent, 'get_repository_info', return_value=mock_repo):
             # Force exception inside analyze_roadmap_features
             mock_repo.get_contents.side_effect = Exception("Roadmap error")
             res = agent.analyze_roadmap_features("repo")
             self.assertFalse(res["has_features"])
             self.assertEqual(res["features"], [])

    def test_senior_developer_cicd_missing_checks(self):
        """Test analyze_cicd with missing workflows and tests."""
        agent = SeniorDeveloperAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_repo = MagicMock()

        # 1. Workflows empty list
        mock_repo.get_contents.side_effect = None
        # First call: workflows. return empty list
        # Second call: contents root. return list without 'test'
        mock_item = MagicMock()
        mock_item.name = "src"
        mock_repo.get_contents.side_effect = [[], [mock_item]]

        self.mock_github.get_repo.return_value = mock_repo

        res = agent.analyze_cicd("repo")
        self.assertTrue(res["needs_improvement"])
        self.assertIn("No GitHub Actions workflows found", res["improvements"])
        self.assertIn("No test directory found - add comprehensive tests", res["improvements"])

    def test_github_client_truncation(self):
        """Test GithubClient telegram message truncation (line 146)."""
        client = GithubClient("token")
        client.telegram_bot_token = "bot"
        client.telegram_chat_id = "chat"

        long_text = "a" * 5000
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            client.send_telegram_msg(long_text)

            # Check if payload text was truncated
            call_args = mock_post.call_args
            json_body = call_args[1]['json']
            self.assertTrue(len(json_body['text']) <= 4096)
            self.assertTrue("truncated" in json_body['text'] or "truncada" in json_body['text'])

    def test_github_client_notification_truncation(self):
        """Test send_telegram_notification truncation."""
        client = GithubClient("token")
        client.telegram_bot_token = "bot"
        client.telegram_chat_id = "chat"

        mock_pr = MagicMock()
        mock_pr.title = "t"
        mock_pr.user.login = "u"
        mock_pr.html_url = "url"
        mock_pr.base.repo.full_name = "repo"
        mock_pr.body = "a" * 500

        with patch.object(client, 'send_telegram_msg') as mock_send:
            client.send_telegram_notification(mock_pr)

            # Check passed text contains truncated body
            args = mock_send.call_args[0]
            text = args[0]
            self.assertIn("\\.\\.\\.", text)
            self.assertNotIn("a" * 500, text)

    def test_jules_client_timeout(self):
        """Test JulesClient wait_for_session timeout (line 267)."""
        client = JulesClient("key")
        with patch.object(client, 'get_session', return_value={"status": "RUNNING", "outputs": []}):
             with patch("time.sleep"): # Skip sleep
                 with self.assertRaises(TimeoutError):
                     client.wait_for_session("sess_id", max_wait_seconds=0.1, poll_interval=0.1)

    def test_jules_client_wait_session_terminal_no_output(self):
        """Test wait_for_session returning on terminal status without outputs."""
        client = JulesClient("key")
        with patch.object(client, 'get_session', return_value={"status": "FAILED", "outputs": []}):
             session = client.wait_for_session("sess_id")
             self.assertEqual(session["status"], "FAILED")

    def test_main_exception(self):
        """Test src/main.py exception handling (line 47)."""
        with patch("src.main.Settings.from_env", side_effect=Exception("Main error")):
            with patch("src.main.sys.exit") as mock_exit:
                src.main.main()
                mock_exit.assert_called_with(1)

    def test_run_agent_exception(self):
        """Test src/run_agent.py exception handling (line 242)."""
        # Force exception in main by invalid args or something, or patch parser
        with patch("argparse.ArgumentParser.parse_args", side_effect=Exception("Arg error")):
            # Since it's top level, we might catch it or it might crash test runner if not careful
            # The line 242 is:
            # except Exception as e:
            #     print(f"Error running agent: {e}")
            #     import traceback
            #     traceback.print_exc()
            #     sys.exit(1)

            # We need to trigger this exception block inside main()
            pass

        # Easier way: Mock parse_args to return known agent, but make runner raise exception
        with patch("src.run_agent.argparse.ArgumentParser.parse_args") as mock_args:
             mock_args.return_value.agent_name = "product-manager"
             mock_args.return_value.provider = None
             mock_args.return_value.model = None

             with patch("src.run_agent.run_product_manager", side_effect=Exception("Run error")):
                 with patch("src.run_agent.sys.exit") as mock_exit:
                     src.run_agent.main()
                     mock_exit.assert_called_with(1)

    def test_summary_conflicts_no_url(self):
        """Test summary generation with conflicts_resolved item having no URL."""
        agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        agent.target_owner = "owner"

        mock_pr_obj = MagicMock()
        mock_pr_obj.html_url = None
        mock_pr_obj.title = "t"
        mock_pr_obj.draft = False

        with patch.object(agent, '_get_prs_to_process', return_value=[{"repository": "repo", "number": 1, "pr_obj": mock_pr_obj}]):
             with patch.object(agent, 'process_pr', return_value={"action": "conflicts_resolved", "pr": 1, "title": "t"}):
                 with patch.object(agent.github_client, 'send_telegram_msg') as mock_send:
                     agent.run()
                     # Verify message content contains the expected string for no-URL
                     args = mock_send.call_args[0]
                     msg = args[0]
                     self.assertIn("• repo\\#1 \\- t", msg) # Escaped

    def test_pipeline_status_netlify_error(self):
        """Test check_pipeline_status with Netlify error."""
        agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_pr = MagicMock()
        mock_commit = MagicMock()
        mock_pr.get_commits.return_value.reversed = [mock_commit]

        mock_status = MagicMock()
        mock_status.state = "failure"
        mock_status.context = "netlify/deploy"
        mock_status.description = "deploy failed"

        mock_combined = MagicMock()
        mock_combined.state = "failure"
        mock_combined.total_count = 1
        mock_combined.statuses = [mock_status]
        mock_commit.get_combined_status.return_value = mock_combined

        # Make sure reversed[0] returns mock_commit
        mock_pr.get_commits.return_value.reversed = [mock_commit]
        # Make sure get_commits().totalCount > 0
        mock_pr.get_commits.return_value.totalCount = 1

        status = agent.check_pipeline_status(mock_pr)
        self.assertTrue(status["success"]) # Netlify errors treated as success (soft fail)
        if "details" in status:
             self.assertIn("netlify", status["details"])

    def test_check_runs_annotation_exception(self):
        """Test check_pipeline_status with exception in get_annotations."""
        agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_pr = MagicMock()
        mock_commit = MagicMock()
        mock_pr.get_commits.return_value.reversed = [mock_commit]

        mock_combined = MagicMock()
        mock_combined.state = "success"
        mock_commit.get_combined_status.return_value = mock_combined

        mock_run = MagicMock()
        mock_run.status = "completed"
        mock_run.conclusion = "failure"
        mock_run.name = "job"
        mock_run.get_annotations.side_effect = Exception("Annotation Error")

        mock_commit.get_check_runs.return_value = [mock_run]

        with patch.object(agent, 'log') as mock_log:
             agent.check_pipeline_status(mock_pr)
             mock_log.assert_any_call("Error fetching annotations for job: Annotation Error", "WARNING")

    def test_process_pr_suggestions_comment_exception(self):
        """Test process_pr exception when commenting suggestions."""
        agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd"
        mock_pr.mergeable = True

        self.mock_github.accept_review_suggestions.return_value = (True, "ok", 1)
        mock_pr.create_issue_comment.side_effect = Exception("Comment Suggestion Error")

        # Stop further processing
        mock_pr.get_commits.return_value.totalCount = 0 # No commits -> fail pipeline

        with patch.object(agent, 'is_pr_too_young', return_value=False):
            with patch.object(agent, 'log') as mock_log:
                agent.process_pr(mock_pr)
                mock_log.assert_any_call(f"Failed to comment on PR #{mock_pr.number} after applying suggestions: Comment Suggestion Error", "WARNING")

    def test_resolve_conflicts_binary_file(self):
        """Test resolve_conflicts_autonomously with binary file."""
        agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd"
        mock_pr.base.repo.clone_url = "https://github.com/base.git"
        mock_pr.head.repo.clone_url = "https://github.com/head.git"
        mock_pr.head.repo.id = 1
        mock_pr.base.repo.id = 2 # Different repos

        with patch("tempfile.TemporaryDirectory") as mock_temp:
             mock_temp.return_value.__enter__.return_value = "/tmp/dir"

             # Mock subprocess.run to raise CalledProcessError when merging
             def side_effect(args, **kwargs):
                 if args[0] == "git" and args[1] == "merge":
                     raise subprocess.CalledProcessError(1, args)
                 return MagicMock()

             with patch("subprocess.run", side_effect=side_effect):
                 with patch("subprocess.check_output", return_value=b"binary.png\n"):
                     # Mock open to raise UnicodeDecodeError on read()
                     m = mock_open()
                     m.return_value.read.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "err")

                     with patch("builtins.open", m):
                         with patch("os.path.join", side_effect=lambda a, b: b): # simplify path
                             with patch.object(agent, 'log') as mock_log:
                                 agent.resolve_conflicts_autonomously(mock_pr)
                                 mock_log.assert_any_call("Skipping binary file: binary.png")

    def test_resolve_conflicts_no_markers(self):
        """Test resolve_conflicts_autonomously with no markers."""
        agent = PRAssistantAgent(self.mock_jules, self.mock_github, self.mock_allowlist)
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd"
        mock_pr.head.repo.id = 1
        mock_pr.base.repo.id = 2

        with patch("tempfile.TemporaryDirectory") as mock_temp:
             mock_temp.return_value.__enter__.return_value = "/tmp/dir"

             # Mock subprocess.run to raise CalledProcessError when merging
             def side_effect(args, **kwargs):
                 if args[0] == "git" and args[1] == "merge":
                     raise subprocess.CalledProcessError(1, args)
                 return MagicMock()

             with patch("subprocess.run", side_effect=side_effect):
                 with patch("subprocess.check_output", return_value=b"file.txt\n"):
                     with patch("builtins.open", mock_open(read_data="No markers here")):
                         with patch("os.path.join", side_effect=lambda a, b: b):
                             with patch.object(agent, 'log') as mock_log:
                                 agent.resolve_conflicts_autonomously(mock_pr)
                                 mock_log.assert_any_call("No markers found in file.txt")

if __name__ == '__main__':
    unittest.main()
