import unittest
from unittest.mock import MagicMock, mock_open, patch

from src.agents.base_agent import BaseAgent
from src.config.repository_allowlist import RepositoryAllowlist
from src.github_client import GithubClient
from src.jules.client import JulesClient


class TestBaseAgent(unittest.TestCase):
    def setUp(self):
        self.mock_jules = MagicMock(spec=JulesClient)
        self.mock_github = MagicMock(spec=GithubClient)
        self.mock_allowlist = MagicMock(spec=RepositoryAllowlist)

        class ConcreteAgent(BaseAgent):
            @property
            def persona(self): return "Test Persona"
            @property
            def mission(self): return "Test Mission"
            def run(self): return {}

        self.agent = ConcreteAgent(self.mock_jules, self.mock_github, self.mock_allowlist, name="test_agent")

    def test_load_instructions_success(self):
        with patch("builtins.open", mock_open(read_data="Test Instructions")):
            with patch("pathlib.Path.exists", return_value=True):
                instructions = self.agent.load_instructions()
                self.assertEqual(instructions, "Test Instructions")
                # Check cache
                self.assertEqual(self.agent._instructions_cache, "Test Instructions")

    def test_load_instructions_not_found(self):
        with patch("pathlib.Path.exists", return_value=False):
            instructions = self.agent.load_instructions()
            self.assertEqual(instructions, "")

    def test_load_instructions_error(self):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", side_effect=Exception("Read error")):
                instructions = self.agent.load_instructions()
                self.assertEqual(instructions, "")

    def test_load_jules_instructions(self):
        template_content = "Repo: {{repository}}"
        with patch("builtins.open", mock_open(read_data=template_content)):
             with patch("pathlib.Path.exists", return_value=True):
                 result = self.agent.load_jules_instructions(variables={"repository": "owner/repo"})
                 self.assertEqual(result, "Repo: owner/repo")

    def test_load_jules_instructions_not_found(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = self.agent.load_jules_instructions()
            self.assertEqual(result, "")

    def test_load_jules_instructions_error(self):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", side_effect=Exception("Error")):
                result = self.agent.load_jules_instructions()
                self.assertEqual(result, "")

    def test_get_instructions_section(self):
        content = """# Header
## Persona
Test Persona Content
## Mission
Test Mission Content
"""
        with patch("builtins.open", mock_open(read_data=content)):
            with patch("pathlib.Path.exists", return_value=True):
                section = self.agent.get_instructions_section("## Persona")
                self.assertEqual(section, "Test Persona Content")

                section = self.agent.get_instructions_section("## Mission")
                self.assertEqual(section, "Test Mission Content")

    def test_get_instructions_section_nested(self):
        content = """# Header
## Persona
Test Persona Content
### Subheader
Subcontent
## Mission
Test Mission Content
"""
        with patch("builtins.open", mock_open(read_data=content)):
            with patch("pathlib.Path.exists", return_value=True):
                section = self.agent.get_instructions_section("## Persona")
                # Should capture until next ## header
                self.assertIn("Test Persona Content", section)
                self.assertIn("### Subheader", section)
                self.assertIn("Subcontent", section)
                self.assertNotIn("## Mission", section)

    def test_get_allowed_repositories(self):
        self.mock_allowlist.list_repositories.return_value = ["repo1"]
        self.assertEqual(self.agent.get_allowed_repositories(), ["repo1"])

    def test_can_work_on_repository(self):
        self.mock_allowlist.is_allowed.return_value = True
        self.assertTrue(self.agent.can_work_on_repository("repo"))

    def test_create_jules_session(self):
        self.mock_allowlist.is_allowed.return_value = True
        self.mock_jules.create_pull_request_session.return_value = {"id": "session1"}

        result = self.agent.create_jules_session("repo", "instructions", "title")
        self.assertEqual(result, {"id": "session1"})

    def test_create_jules_session_wait(self):
        self.mock_allowlist.is_allowed.return_value = True
        self.mock_jules.create_pull_request_session.return_value = {"id": "session1"}
        self.mock_jules.wait_for_session.return_value = {"status": "completed"}

        self.agent.create_jules_session("repo", "instructions", "title", wait_for_completion=True)
        self.mock_jules.wait_for_session.assert_called_with("session1")

    def test_create_jules_session_not_allowed(self):
        self.mock_allowlist.is_allowed.return_value = False
        with self.assertRaises(ValueError):
            self.agent.create_jules_session("repo", "instr", "title")

    def test_get_repository_info(self):
        self.mock_github.get_repo.return_value = "repo_obj"
        self.assertEqual(self.agent.get_repository_info("repo"), "repo_obj")

    def test_get_repository_info_error(self):
        self.mock_github.get_repo.side_effect = Exception("Error")
        self.assertIsNone(self.agent.get_repository_info("repo"))
