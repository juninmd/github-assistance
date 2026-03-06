import os
import unittest
from unittest.mock import MagicMock, patch

from github import GithubException

from src.github_client import GithubClient


class TestGithubClient(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {"GITHUB_TOKEN": "token"})
        self.env_patcher.start()

        self.github_patcher = patch("src.github_client.Github")
        self.mock_github_cls = self.github_patcher.start()
        self.mock_github_instance = self.mock_github_cls.return_value

        self.client = GithubClient()

    def tearDown(self):
        self.env_patcher.stop()
        self.github_patcher.stop()

    def test_init(self):
        self.assertEqual(self.client.token, "token")
        self.mock_github_cls.assert_called_once()

    def test_init_missing_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GITHUB_TOKEN"):
                GithubClient()

    def test_search_prs(self):
        self.mock_github_instance.search_issues.return_value = ["pr1"]
        result = self.client.search_prs("query")
        self.assertEqual(result, ["pr1"])
        self.mock_github_instance.search_issues.assert_called_with("query")

    def test_get_pr_from_issue(self):
        issue = MagicMock()
        issue.as_pull_request.return_value = "pr"
        result = self.client.get_pr_from_issue(issue)
        self.assertEqual(result, "pr")

    def test_get_repo(self):
        self.mock_github_instance.get_repo.return_value = "repo"
        result = self.client.get_repo("name")
        self.assertEqual(result, "repo")
        self.mock_github_instance.get_repo.assert_called_with("name")

    def test_merge_pr_success(self):
        pr = MagicMock()
        result = self.client.merge_pr(pr)
        pr.merge.assert_called()
        self.assertEqual(result, (True, "Merged successfully"))

    def test_merge_pr_failure(self):
        pr = MagicMock()
        pr.merge.side_effect = GithubException(400, "Error")
        result = self.client.merge_pr(pr)
        self.assertEqual(result[0], False)
        self.assertIn("Error", result[1])

    def test_comment_on_pr(self):
        pr = MagicMock()
        self.client.comment_on_pr(pr, "body")
        pr.create_issue_comment.assert_called_with("body")

    def test_get_issue_comments(self):
        pr = MagicMock()
        pr.get_issue_comments.return_value = ["c1"]
        result = self.client.get_issue_comments(pr)
        self.assertEqual(result, ["c1"])

    def test_add_label_to_pr(self):
        pr = MagicMock()
        self.client.add_label_to_pr(pr, "auto-merge")
        pr.as_issue.return_value.add_to_labels.assert_called_with("auto-merge")

    def test_add_label_to_pr_failure(self):
        pr = MagicMock()
        pr.as_issue.return_value.add_to_labels.side_effect = GithubException(400, "Error")
        success, msg = self.client.add_label_to_pr(pr, "auto-merge")
        self.assertFalse(success)
        self.assertIn("Error", msg)

    def test_commit_file_success(self):
        pr = MagicMock()
        repo = pr.base.repo
        contents = MagicMock()
        contents.path = "path"
        contents.sha = "sha"
        repo.get_contents.return_value = contents

        result = self.client.commit_file(pr, "path", "content", "msg")
        self.assertTrue(result)
        repo.update_file.assert_called()

    def test_commit_file_failure(self):
        pr = MagicMock()
        repo = pr.base.repo
        repo.get_contents.side_effect = GithubException(404, "Not found")

        result = self.client.commit_file(pr, "path", "content", "msg")
        self.assertFalse(result)

    def test_close_pr_success(self):
        pr = MagicMock()
        success, msg = self.client.close_pr(pr)
        self.assertTrue(success)
        pr.edit.assert_called_with(state="closed")

    def test_close_pr_failure(self):
        pr = MagicMock()
        pr.edit.side_effect = GithubException(400, "Error")
        success, msg = self.client.close_pr(pr)
        self.assertFalse(success)

    def test_normalize_login(self):
        self.assertEqual(GithubClient._normalize_login("user[bot]"), "user")
        self.assertEqual(GithubClient._normalize_login("User"), "user")
        self.assertEqual(GithubClient._normalize_login(None), "")  # type: ignore
