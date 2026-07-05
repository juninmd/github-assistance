import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from github import GithubException

from src.agents.product_manager.utils import (
    analyze_issues_with_ai_logic,
    analyze_repository,
    generate_roadmap_instructions,
    is_roadmap_up_to_date,
)


class TestProductManagerUtilsCoverage(unittest.TestCase):
    def test_is_roadmap_up_to_date(self):
        repo = MagicMock()
        log_func = MagicMock()

        # No commits
        repo.get_commits.return_value = []
        self.assertFalse(is_roadmap_up_to_date(repo, log_func))

        # Fresh commit
        commit = MagicMock()
        commit.commit.author.date = datetime.now(UTC) - timedelta(days=2)
        repo.get_commits.return_value = [commit]
        self.assertTrue(is_roadmap_up_to_date(repo, log_func))
        log_func.assert_called_with("ROADMAP.md updated 2d ago — still fresh")

        # Stale commit
        commit_stale = MagicMock()
        commit_stale.commit.author.date = datetime.now(UTC) - timedelta(days=10)
        repo.get_commits.return_value = [commit_stale]
        self.assertFalse(is_roadmap_up_to_date(repo, log_func))

        # GithubException
        repo.get_commits.side_effect = GithubException(500, "Error")
        self.assertFalse(is_roadmap_up_to_date(repo, log_func))

        # Other Exception
        repo.get_commits.side_effect = Exception("Unexpected error")
        self.assertFalse(is_roadmap_up_to_date(repo, log_func))
        log_func.assert_called_with("Error checking ROADMAP.md freshness: Unexpected error", "WARNING")

    def test_analyze_issues_with_ai_logic(self):
        ai_client = MagicMock()
        log_func = MagicMock()

        # No ai_client or no issues
        self.assertEqual(analyze_issues_with_ai_logic(None, [MagicMock()], "desc"), {})
        self.assertEqual(analyze_issues_with_ai_logic(ai_client, [], "desc"), {})

        # Successful generation
        issue1 = MagicMock()
        issue1.number = 1
        issue1.title = "Bug 1"
        label1 = MagicMock()
        label1.name = "bug"
        issue1.labels = [label1]

        ai_client.generate.return_value = '{"ai_summary": "Summary text", "priorities": [{"category": "Bugs", "count": 1, "urgency": "high"}]}'
        result = analyze_issues_with_ai_logic(ai_client, [issue1], "desc", log_func)
        self.assertEqual(result["ai_summary"], "Summary text")
        self.assertEqual(result["priorities"][0]["category"], "Bugs")

        # Regex mismatch (no braces)
        ai_client.generate.return_value = "no json here"
        result_err = analyze_issues_with_ai_logic(ai_client, [issue1], "desc", log_func)
        self.assertEqual(result_err, {})
        log_func.assert_any_call("Could not find JSON in AI response", "WARNING")

        # JSON Decode error from json.loads (braces exist but invalid JSON)
        ai_client.generate.return_value = "{invalid json}"
        result_json_err = analyze_issues_with_ai_logic(ai_client, [issue1], "desc", log_func)
        self.assertEqual(result_json_err, {})

        # Exception from AI client
        ai_client.generate.side_effect = Exception("AI failure")
        result_fail = analyze_issues_with_ai_logic(ai_client, [issue1], "desc", log_func)
        self.assertEqual(result_fail, {})
        log_func.assert_called_with("AI client failed to generate response: AI failure", "WARNING")

    def test_analyze_repository(self):
        repo_info = MagicMock()
        ai_client = MagicMock()
        log_func = MagicMock()

        repo_info.description = "Test Description"
        repo_info.language = "Python"

        # Mock get_issues with proper label names
        label_bug = MagicMock()
        label_bug.name = "bug"

        label_feat = MagicMock()
        label_feat.name = "feature"

        label_tech = MagicMock()
        label_tech.name = "refactor"

        issue_bug = MagicMock()
        issue_bug.labels = [label_bug]
        issue_bug.number = 1
        issue_bug.title = "issue 1"

        issue_feat = MagicMock()
        issue_feat.labels = [label_feat]
        issue_feat.number = 2
        issue_feat.title = "issue 2"

        issue_tech = MagicMock()
        issue_tech.labels = [label_tech]
        issue_tech.number = 3
        issue_tech.title = "issue 3"

        repo_info.get_issues.return_value = [issue_bug, issue_feat, issue_tech]

        # Mock AI logic returning empty
        ai_client.generate.return_value = ""

        result = analyze_repository("owner/repo", repo_info, ai_client, log_func)
        self.assertEqual(result["total_issues"], 3)
        self.assertEqual(result["repository_description"], "Test Description")
        self.assertEqual(result["primary_language"], "Python")
        self.assertIn("Repository has 3 open issues", result["summary"])
        self.assertEqual(len(result["priorities"]), 3)

        # AI returning valid response
        ai_client.generate.return_value = '{"ai_summary": "AI summary text", "priorities": [{"category": "AI Priority", "count": 1, "urgency": "medium"}]}'
        result_ai = analyze_repository("owner/repo", repo_info, ai_client, log_func)
        self.assertEqual(result_ai["summary"], "AI summary text")
        self.assertEqual(result_ai["priorities"][0]["category"], "AI Priority")

    def test_generate_roadmap_instructions(self):
        load_func = MagicMock(return_value="Instruction output")
        analysis = {
            "repository_description": "My Desc",
            "primary_language": "TypeScript",
            "total_issues": 5,
            "priorities": [{"category": "Bugs", "count": 2, "urgency": "high"}]
        }
        res = generate_roadmap_instructions(analysis, load_func, "owner/repo")
        self.assertEqual(res, "Instruction output")
        load_func.assert_called_once()
