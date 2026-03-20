import unittest
from unittest.mock import MagicMock

from src.agents.pr_assistant.utils import get_prs_to_process, is_trusted_author

class TestPRAssistantUtils(unittest.TestCase):
    def test_get_prs_to_process_with_ref_success(self):
        github_client = MagicMock()
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        github_client.get_repo.return_value = mock_repo

        prs = get_prs_to_process(github_client, "target_owner", "owner/repo#123")

        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0], mock_pr)
        github_client.get_repo.assert_called_once_with("owner/repo")
        mock_repo.get_pull.assert_called_once_with(123)

    def test_get_prs_to_process_with_ref_exception(self):
        github_client = MagicMock()
        github_client.get_repo.side_effect = Exception("Repo not found")

        prs = get_prs_to_process(github_client, "target_owner", "owner/repo#123")

        self.assertEqual(len(prs), 0)

    def test_get_prs_to_process_without_ref_success(self):
        github_client = MagicMock()
        mock_issue1 = MagicMock()
        mock_issue2 = MagicMock()
        github_client.search_prs.return_value = [mock_issue1, mock_issue2]

        mock_pr1 = MagicMock()
        mock_pr2 = MagicMock()
        github_client.get_pr_from_issue.side_effect = [mock_pr1, mock_pr2]

        prs = get_prs_to_process(github_client, "target_owner", None)

        self.assertEqual(len(prs), 2)
        self.assertEqual(prs[0], mock_pr1)
        self.assertEqual(prs[1], mock_pr2)
        github_client.search_prs.assert_called_once_with("is:pr is:open archived:false user:target_owner")

    def test_get_prs_to_process_without_ref_with_exception(self):
        github_client = MagicMock()
        mock_issue1 = MagicMock()
        mock_issue2 = MagicMock()
        github_client.search_prs.return_value = [mock_issue1, mock_issue2]

        mock_pr1 = MagicMock()
        # Second issue fails
        github_client.get_pr_from_issue.side_effect = [mock_pr1, Exception("Failed to get PR")]

        prs = get_prs_to_process(github_client, "target_owner", None)

        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0], mock_pr1)

    def test_is_trusted_author(self):
        allowed_authors = ["jules", "bot[bot]", "admin"]

        self.assertTrue(is_trusted_author("jules", allowed_authors))
        self.assertTrue(is_trusted_author("JULES", allowed_authors))
        self.assertTrue(is_trusted_author("bot", allowed_authors))
        self.assertTrue(is_trusted_author("bot[bot]", allowed_authors))
        self.assertTrue(is_trusted_author("admin", allowed_authors))

        self.assertFalse(is_trusted_author("unknown", allowed_authors))
        self.assertFalse(is_trusted_author("hacker", allowed_authors))

if __name__ == "__main__":
    unittest.main()
