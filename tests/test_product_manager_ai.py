"""Tests for the ProductManager AI analysis helper and the new AIClient.generate() method."""
import unittest
from unittest.mock import MagicMock, patch

from src.agents.product_manager.ai_analysis import analyze_issues_with_ai
from src.ai_client import GeminiClient, OllamaClient, OpenAIClient


def _mock_label(name: str):
    label = MagicMock()
    label.name = name
    return label


def _mock_issue(number, title, labels=None):
    issue = MagicMock()
    issue.number = number
    issue.title = title
    issue.labels = [_mock_label(lb) for lb in (labels or [])]
    return issue


class TestAnalyzeIssuesWithAI(unittest.TestCase):
    def test_no_issues_returns_defaults(self):
        client = MagicMock()
        result = analyze_issues_with_ai(client, [], "some repo")
        self.assertEqual(result["ai_summary"], "No open issues to analyse.")
        self.assertEqual(result["ai_priorities"], [])
        self.assertEqual(result["ai_highlights"], [])
        client.generate.assert_not_called()

    def test_parses_structured_response(self):
        client = MagicMock()
        client.generate.return_value = (
            "SUMMARY: The repo needs security fixes urgently. Auth issues dominate.\n"
            "PRIORITY: Fix authentication vulnerabilities\n"
            "PRIORITY: Improve test coverage\n"
            "PRIORITY: Refactor legacy modules\n"
            "HIGHLIGHT: #7 SQL injection in login endpoint\n"
            "HIGHLIGHT: #12 Missing rate limiting\n"
        )
        issues = [_mock_issue(7, "SQL injection in login endpoint", ["bug"])]
        result = analyze_issues_with_ai(client, issues, "A web app")

        self.assertIn("security fixes", result["ai_summary"])
        self.assertEqual(len(result["ai_priorities"]), 3)
        self.assertIn("authentication vulnerabilities", result["ai_priorities"][0])
        self.assertEqual(len(result["ai_highlights"]), 2)

    def test_handles_ai_exception_gracefully(self):
        client = MagicMock()
        client.generate.side_effect = RuntimeError("model unavailable")
        issues = [_mock_issue(1, "Crash on startup")]
        result = analyze_issues_with_ai(client, issues, "A CLI tool")

        self.assertIn("AI analysis unavailable", result["ai_summary"])
        self.assertEqual(result["ai_priorities"], [])
        self.assertEqual(result["ai_highlights"], [])

    def test_limits_priorities_to_three(self):
        client = MagicMock()
        client.generate.return_value = (
            "SUMMARY: Many issues.\n"
            "PRIORITY: One\nPRIORITY: Two\nPRIORITY: Three\nPRIORITY: Four\n"
        )
        issues = [_mock_issue(1, "Issue")]
        result = analyze_issues_with_ai(client, issues, "repo")
        self.assertEqual(len(result["ai_priorities"]), 3)

    def test_truncates_issues_to_forty(self):
        client = MagicMock()
        client.generate.return_value = "SUMMARY: OK.\n"
        issues = [_mock_issue(i, f"Issue {i}") for i in range(60)]
        analyze_issues_with_ai(client, issues, "repo")
        prompt_arg = client.generate.call_args[0][0]
        # Only 40 issues should appear in the prompt
        self.assertEqual(prompt_arg.count("#"), 40)


class TestAIClientGenerate(unittest.TestCase):
    @patch("src.ai_client.ollama.Client")
    def test_ollama_generate_delegates_to_internal(self, mock_cls):
        mock_cls.return_value.generate.return_value = {"response": "great answer"}
        client = OllamaClient()
        result = client.generate("What is 2+2?")
        self.assertEqual(result, "great answer")

    def test_openai_generate_delegates_to_internal(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": "  openai response  "}}]
            }
            mock_post.return_value.raise_for_status = MagicMock()
            client = OpenAIClient(api_key="test-key")
            result = client.generate("Hello")
            self.assertEqual(result, "openai response")

    def test_gemini_generate_raises_without_api_key(self):
        client = GeminiClient(api_key=None)
        if client.client is None:
            with self.assertRaises(ValueError):
                client.generate("Hello")

    @patch("google.genai.Client")
    def test_gemini_generate_calls_model(self, mock_cls):
        mock_cls.return_value.models.generate_content.return_value.text = "gemini says hi"
        client = GeminiClient(api_key="test")
        result = client.generate("Hello")
        self.assertEqual(result, "gemini says hi")


class TestProductManagerAIInit(unittest.TestCase):
    def _make_agent(self, **kwargs):
        from src.agents.product_manager.agent import ProductManagerAgent
        return ProductManagerAgent(
            jules_client=MagicMock(),
            github_client=MagicMock(),
            allowlist=MagicMock(),
            **kwargs,
        )

    @patch("src.agents.product_manager.agent.get_ai_client")
    def test_ai_client_initialized_with_defaults(self, mock_factory):
        mock_factory.return_value = MagicMock()
        agent = self._make_agent()
        mock_factory.assert_called_once_with("ollama", model="llama3")
        self.assertIsNotNone(agent._ai_client)

    @patch("src.agents.product_manager.agent.get_ai_client")
    def test_ai_client_none_when_factory_raises(self, mock_factory):
        mock_factory.side_effect = Exception("connection refused")
        agent = self._make_agent()
        self.assertIsNone(agent._ai_client)

    @patch("src.agents.product_manager.agent.get_ai_client")
    @patch("src.agents.product_manager.agent.analyze_issues_with_ai")
    def test_analyze_repository_calls_ai(self, mock_ai_analysis, mock_factory):
        mock_factory.return_value = MagicMock()
        mock_ai_analysis.return_value = {
            "ai_summary": "Needs more tests.",
            "ai_priorities": ["Write unit tests", "Fix CI"],
            "ai_highlights": ["#3 Flaky test suite"],
        }
        agent = self._make_agent()

        repo_info = MagicMock()
        repo_info.get_issues.return_value = [_mock_issue(1, "Flaky test", ["bug"])]
        repo_info.description = "A Python library"
        repo_info.language = "Python"

        result = agent.analyze_repository("owner/repo", repo_info)

        mock_ai_analysis.assert_called_once()
        self.assertEqual(result["summary"], "Needs more tests.")
        self.assertEqual(result["ai_priorities"], ["Write unit tests", "Fix CI"])

    @patch("src.agents.product_manager.agent.get_ai_client")
    def test_analyze_repository_skips_ai_when_client_none(self, mock_factory):
        mock_factory.side_effect = Exception("no ollama")
        agent = self._make_agent()

        repo_info = MagicMock()
        repo_info.get_issues.return_value = []
        repo_info.description = "A repo"
        repo_info.language = "Go"

        result = agent.analyze_repository("owner/repo", repo_info)
        self.assertIn("0 open issues", result["summary"])
