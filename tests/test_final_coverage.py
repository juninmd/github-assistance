import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from github import GithubException

from src.agents.pr_assistant import PRAssistantAgent
from src.agents.senior_developer import SeniorDeveloperAgent
from src.github_client import GithubClient
from src.main import main


class TestGithubClientCoverage(unittest.TestCase):
    def test_init_no_token(self):
        """Test initialization raises ValueError when GITHUB_TOKEN is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as cm:
                GithubClient(token=None)
            self.assertEqual(str(cm.exception), "GITHUB_TOKEN is required")

    def test_merge_pr_exception(self):
        """Test merge_pr handles GithubException."""
        client = GithubClient(token="test")
        mock_pr = MagicMock()
        mock_pr.merge.side_effect = GithubException(404, "Not Found", {})

        success, msg = client.merge_pr(mock_pr)
        self.assertFalse(success)
        self.assertIn("404", msg)

    def test_commit_file_exception(self):
        """Test commit_file handles GithubException."""
        client = GithubClient(token="test")
        mock_pr = MagicMock()
        mock_pr.base.repo.get_contents.side_effect = GithubException(500, "Server Error", {})

        # Should return False and print error (we can just check return value)
        result = client.commit_file(mock_pr, "file.txt", "content", "msg")
        self.assertFalse(result)

    def test_accept_review_suggestions_exception(self):
        """Test accept_review_suggestions handles generic Exception."""
        client = GithubClient(token="test")
        mock_pr = MagicMock()
        mock_pr.get_review_comments.side_effect = Exception("Boom")

        success, msg, count = client.accept_review_suggestions(mock_pr, ["bot"])
        self.assertFalse(success)
        self.assertIn("Boom", msg)
        self.assertEqual(count, 0)



class TestPRAssistantCoverage(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.agent = PRAssistantAgent(
            jules_client=self.mock_jules,
            github_client=self.mock_github,
            allowlist=self.mock_allowlist,
            target_owner="juninmd"
        )
        # Prevent date math errors by mocking age check
        self.agent.is_pr_too_young = MagicMock(return_value=False)
        # Mock suggestions response
        self.mock_github.accept_review_suggestions.return_value = (True, "OK", 0)

    def test_check_pipeline_status_pending(self):
        """Test check_pipeline_status handles pending state."""
        mock_pr = MagicMock()
        mock_pr.get_commits.return_value.reversed = [MagicMock()]
        mock_commit = mock_pr.get_commits.return_value.reversed[0]

        # Combined status pending
        mock_commit.get_combined_status.return_value.state = 'pending'
        mock_commit.get_combined_status.return_value.total_count = 1
        mock_commit.get_combined_status.return_value.statuses = [
            MagicMock(state='pending', context='ci', description='Pending')
        ]

        status = self.agent.check_pipeline_status(mock_pr)
        self.assertFalse(status['success'])
        self.assertEqual(status['reason'], 'pending')

    def test_process_pr_add_label_failure(self):
        """Test process_pr handles failure to add label."""
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd"
        mock_pr.mergeable = True

        # Pipeline success
        self.agent.check_pipeline_status = MagicMock(return_value={"success": True})

        # Merge success
        self.mock_github.merge_pr.return_value = (True, "merged")

        # Label failure
        self.mock_github.add_label_to_pr = MagicMock(return_value=(False, "Label error"))

        result = self.agent.process_pr(mock_pr)

        # Should still merge, just warn about label
        self.assertEqual(result['action'], 'merged')
        # We can't easily assert the warning log without mocking self.log or stdout capture,
        # but coverage should be hit.

    def test_handle_pipeline_failure_existing_comment(self):
        """Test handle_pipeline_failure skips if comment exists."""
        mock_pr = MagicMock()
        mock_pr.number = 123

        # Existing comment
        mock_comment = MagicMock()
        mock_comment.body = "❌ Pipeline Failure Detected"
        self.mock_github.get_issue_comments.return_value = [mock_comment]

        self.agent.handle_pipeline_failure(mock_pr, "details")

        # Should NOT call create_issue_comment
        mock_pr.create_issue_comment.assert_not_called()

    def test_process_pr_pipeline_pending(self):
        """Test process_pr handles pending pipeline."""
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd"
        mock_pr.mergeable = True

        self.agent.check_pipeline_status = MagicMock(return_value={
            "success": False, "reason": "pending", "details": "Pending"
        })

        result = self.agent.process_pr(mock_pr)
        self.assertEqual(result['action'], 'skipped')
        self.assertEqual(result['reason'], 'pipeline_pending')

    def test_process_pr_status_error(self):
        """Test process_pr handles status check error."""
        mock_pr = MagicMock()
        mock_pr.user.login = "juninmd"
        mock_pr.mergeable = True

        self.agent.check_pipeline_status = MagicMock(return_value={
            "success": False, "reason": "error", "details": "Error"
        })

        result = self.agent.process_pr(mock_pr)
        self.assertEqual(result['action'], 'skipped')
        self.assertEqual(result['reason'], 'status_error')



class TestSeniorDeveloperCoverage(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock()
        self.mock_github = MagicMock()
        self.mock_allowlist = MagicMock()
        self.agent = SeniorDeveloperAgent(
            jules_client=self.mock_jules,
            github_client=self.mock_github,
            allowlist=self.mock_allowlist
        )

    def test_analysis_methods_exceptions(self):
        """Test analysis methods handle exceptions gracefully."""
        # Mock get_repository_info to raise exception
        self.agent.get_repository_info = MagicMock(side_effect=Exception("Repo Access Error"))

        # All analysis methods should catch the exception and return safe default
        # (usually {needs_*: False} or similar) or log error (which we can't easily assert without log mock)

        # Wait, the methods call get_repository_info internally.
        # If get_repository_info returns None (which base agent does on error usually?), then they return defaults.
        # But if get_repository_info raises, does BaseAgent handle it?
        # Looking at SeniorDev code:
        # repo_info = self.get_repository_info(repository)
        # if not repo_info: return ...

        # So exception in get_repository_info would propagate unless handled there.
        # But here I want to test exceptions *inside* the analysis logic (e.g. repo_info.get_contents fails)

        mock_repo_info = MagicMock()
        mock_repo_info.get_contents.side_effect = Exception("API Error")
        self.agent.get_repository_info = MagicMock(return_value=mock_repo_info)

        # Test analyze_security
        res = self.agent.analyze_security("repo")
        # Should return needs_attention: True because exceptions in checks add to issues list?
        # Code: try: ... except: issues.append(...)
        self.assertTrue(res['needs_attention'])
        self.assertIn("Missing .gitignore", res['issues'][0])

        # Test analyze_cicd
        # Code: try: ... except: improvements.append(...)
        res = self.agent.analyze_cicd("repo")
        self.assertTrue(res['needs_improvement'])
        self.assertIn("Set up GitHub Actions", res['improvements'][0])

        # Test analyze_roadmap_features
        # Code: try: ... except: return {has_features: False}
        res = self.agent.analyze_roadmap_features("repo")
        self.assertFalse(res['has_features'])

        # Test analyze_tech_debt
        # Code: try: ... except: log warning
        res = self.agent.analyze_tech_debt("repo")
        self.assertFalse(res['needs_attention']) # Returns empty/false on error catch

        # Test analyze_modernization
        res = self.agent.analyze_modernization("repo")
        self.assertFalse(res['needs_modernization'])

        # Test analyze_performance
        res = self.agent.analyze_performance("repo")
        self.assertFalse(res['needs_optimization'])

    def test_count_today_sessions_exception(self):
        """Test count_today_sessions handles API error."""
        self.mock_jules.list_sessions.side_effect = Exception("API Error")
        count = self.agent.count_today_sessions_utc_minus_3()
        self.assertEqual(count, 0)

    def test_extract_session_datetime_invalid(self):
        """Test extract_session_datetime handles invalid data."""
        self.assertIsNone(self.agent.extract_session_datetime({}))
        self.assertIsNone(self.agent.extract_session_datetime({"createdAt": "invalid-date"}))

    def test_analysis_branches(self):
        """Test specific branches in analysis methods."""
        mock_repo_info = MagicMock()

        # 1. Security Analysis - Missing .env in gitignore
        mock_gitignore = MagicMock()
        mock_gitignore.decoded_content = b"*.log\n"
        mock_repo_info.get_contents.side_effect = lambda path: mock_gitignore if path == ".gitignore" else MagicMock()
        self.agent.get_repository_info = MagicMock(return_value=mock_repo_info)

        res = self.agent.analyze_security("repo")
        self.assertTrue(res['needs_attention'])
        self.assertIn("Missing .env", res['issues'][0])

        # 2. Performance Analysis - Heavy Dependency
        mock_pkg = MagicMock()
        mock_pkg.decoded_content = b'{"dependencies": {"lodash": "4.17.21"}}'
        mock_repo_info.get_contents.side_effect = lambda path: mock_pkg if path == "package.json" else MagicMock()

        res = self.agent.analyze_performance("repo")
        self.assertTrue(res['needs_optimization'])
        self.assertIn("lodash", res['details'])

        # 3. Tech Debt - Large File
        mock_tree = MagicMock()
        mock_large_file = MagicMock(path="big.py", size=30000)
        mock_tree.tree = [mock_large_file]
        mock_repo_info.get_git_tree.return_value = mock_tree
        # Reset get_contents side effect to avoid errors
        mock_repo_info.get_contents.side_effect = None

        res = self.agent.analyze_tech_debt("repo")
        self.assertTrue(res['needs_attention'])
        self.assertIn("Large file", res['details'])




class TestMainCoverage(unittest.TestCase):
    def test_main_exception(self):
        """Test main handles exception and exits."""
        # Patch Settings.from_env to raise exception
        with patch('src.config.Settings.from_env', side_effect=ValueError("Settings Error")):
            with self.assertRaises(SystemExit) as cm:
                with patch("sys.argv", ["pr-assistant"]):
                    main()
            self.assertEqual(cm.exception.code, 1)

    def test_main_ollama(self):
        """Test main with ollama provider."""
        mock_settings = MagicMock()
        mock_settings.ai_provider = "ollama"
        mock_settings.ollama_base_url = "http://localhost:11434"
        mock_settings.jules_api_key = "key"
        mock_settings.repository_allowlist_path = "path"
        mock_settings.github_owner = "owner"
        mock_settings.ai_model = "llama3"

        with patch('src.config.Settings.from_env', return_value=mock_settings):
            with patch('src.main.GithubClient'):
                with patch('src.main.JulesClient'):
                    with patch('src.main.RepositoryAllowlist'):
                        with patch('src.main.PRAssistantAgent') as MockAgent:
                            mock_instance = MockAgent.return_value
                            with patch("sys.argv", ["pr-assistant"]):
                                main()

                            # Verify ollama config passed
                            args, kwargs = MockAgent.call_args
                            self.assertEqual(kwargs['ai_provider'], "ollama")
                            self.assertEqual(kwargs['ai_config']['base_url'], "http://localhost:11434")
                            mock_instance.run.assert_called_once()
