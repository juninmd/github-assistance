import unittest
from unittest.mock import MagicMock, patch

from src.agents.pr_assistant.agent import PRAssistantAgent


class TestPRAssistantGapsV2(unittest.TestCase):
    def setUp(self):
        with patch("src.agents.pr_assistant.agent.get_ai_client"):
            self.mock_jules = MagicMock()
            self.mock_github = MagicMock()
            self.mock_allowlist = MagicMock()
            self.agent = PRAssistantAgent(
                self.mock_jules,
                self.mock_github,
                self.mock_allowlist,
                target_owner="owner"
            )

    def test_persona_mission(self):
        with patch.object(self.agent, 'get_instructions_section', return_value="Test"):
            self.assertEqual(self.agent.persona, "Test")
            self.assertEqual(self.agent.mission, "Test")

    def test_run_exception_handling(self):
        # Line 161: Exception inside loop
        # Mock _get_prs_to_process to return valid data
        mock_pr = MagicMock()
        mock_pr.draft = False
        with patch.object(self.agent, '_get_prs_to_process', return_value=[{"repository": "owner/repo", "number": 1, "pr_obj": mock_pr}]):
            # Mock process_pr to raise Exception
            with patch.object(self.agent, 'process_pr', side_effect=Exception("Process Error")):
                results = self.agent.run()
                self.assertEqual(len(results["skipped"]), 1)
                self.assertIn("error", results["skipped"][0]["reason"])

    def test_get_prs_specific_repo_number(self):
        # specific_pr="repo#123" -> owner/repo#123
        prs = self.agent._get_prs_to_process("repo#123")
        self.assertEqual(prs[0]["repository"], "owner/repo")
        self.assertEqual(prs[0]["number"], 123)

    def test_get_prs_specific_full_repo_number(self):
        # specific_pr="other/repo#123" -> other/repo#123
        prs = self.agent._get_prs_to_process("other/repo#123")
        self.assertEqual(prs[0]["repository"], "other/repo")
        self.assertEqual(prs[0]["number"], 123)

    def test_get_prs_specific_number_only(self):
        # specific_pr="123" -> search query
        # Mock github_client.search_prs
        mock_issue = MagicMock()
        mock_issue.repository.full_name = "owner/repo"
        mock_issue.number = 123
        self.mock_github.search_prs.return_value = [mock_issue]
        self.mock_github.get_pr_from_issue.return_value = MagicMock()

        prs = self.agent._get_prs_to_process("123")
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["repository"], "owner/repo")
        self.assertEqual(prs[0]["number"], 123)

if __name__ == '__main__':
    unittest.main()
