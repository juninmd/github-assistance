"""Tests for the Secret Remover Agent."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from src.agents.secret_remover.agent import SecretRemoverAgent
from src.agents.secret_remover.ai_analyzer import analyze_finding


class TestAnalyzeFinding(unittest.TestCase):
    def test_delegates_to_structured_classifier(self):
        ai_client = MagicMock()
        ai_client.classify_secret_finding.return_value = {
            "action": "IGNORE",
            "reason": "test fixture",
        }

        finding = {
            "rule_id": "generic-api-key",
            "file": "test.env",
            "line": 1,
            "redacted_context": "> 1: API_KEY = \"<redacted>\"",
        }
        result = analyze_finding(finding, ai_client)

        self.assertEqual(result["action"], "IGNORE")
        ai_client.classify_secret_finding.assert_called_once_with(
            finding=finding,
            redacted_context=finding["redacted_context"],
        )


class TestSecretRemoverAgent(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock()
        self.github_client = MagicMock()
        self.allowlist = MagicMock()
        self.telegram = MagicMock()
        self.telegram.escape = lambda t: t.replace("_", "\\_") if t else ""

        self.agent = SecretRemoverAgent(
            self.jules_client,
            self.github_client,
            self.allowlist,
            telegram=self.telegram,
            target_owner="testowner",
            ai_provider="gemini",
            ai_model="gemini-2.5-flash",
            ai_config={"api_key": "fake"},
        )
        self.agent.get_instructions_section = MagicMock(return_value="Dummy")

    @patch("glob.glob")
    def test_find_latest_results_no_files(self, mock_glob):
        mock_glob.return_value = []
        self.assertIsNone(self.agent._find_latest_results())

    @patch("builtins.open", mock_open(read_data='{"repositories_with_findings": []}'))
    @patch("glob.glob")
    def test_find_latest_results_returns_latest(self, mock_glob):
        mock_glob.return_value = [
            "results/security-scanner_20260101.json",
            "results/security-scanner_20260201.json",
        ]
        result = self.agent._find_latest_results()
        self.assertIsNotNone(result)
        self.assertIn("repositories_with_findings", result or {})

    @patch("builtins.open", mock_open(read_data='{"repositories_with_findings": []}'))
    @patch("glob.glob")
    def test_find_latest_results_searches_repo_root_when_cwd_has_none(self, mock_glob):
        mock_glob.side_effect = [[], ["results/security-scanner_20260201.json"]]
        result = self.agent._find_latest_results()
        self.assertIsNotNone(result)
        self.assertIn("repositories_with_findings", result or {})
        self.assertEqual(mock_glob.call_count, 2)

    @patch("builtins.open", mock_open(read_data='not json'))
    @patch("glob.glob")
    def test_find_latest_results_skips_malformed_json(self, mock_glob):
        mock_glob.return_value = [
            "results/security-scanner_20260301.json",
            "results/security-scanner_20260302.json",
        ]
        mocked_open = mock_open()
        mocked_open.side_effect = [
            mock_open(read_data='not json').return_value,
            mock_open(read_data='{"repositories_with_findings": []}').return_value,
        ]
        with patch("builtins.open", mocked_open):
            result = self.agent._find_latest_results()
        self.assertIsNotNone(result)
        self.assertIn("repositories_with_findings", result or {})

    @patch.object(SecretRemoverAgent, "_find_latest_results", return_value=None)
    def test_run_no_results_sends_error(self, _mock_find):
        result = self.agent.run()
        self.assertIn("error", result)
        self.telegram.send_message.assert_called_once()

    @patch.object(SecretRemoverAgent, "_process_repo")
    @patch.object(SecretRemoverAgent, "_find_latest_results")
    def test_run_processes_repos(self, mock_find, mock_process):
        mock_find.return_value = {
            "repositories_with_findings": [
                {
                    "repository": "owner/repo1",
                    "findings": [{"rule_id": "r1"}],
                    "default_branch": "main",
                },
                {
                    "repository": "owner/repo2",
                    "findings": [{"rule_id": "r2"}],
                    "default_branch": "master",
                },
            ]
        }
        mock_process.return_value = {
            "repository": "owner/repo1",
            "ignored": 1,
            "to_remove": 0,
            "actions": [],
        }

        result = self.agent.run()

        self.assertEqual(result["total_repos_processed"], 2)
        self.assertEqual(mock_process.call_count, 2)

    @patch.object(SecretRemoverAgent, "_process_repo", side_effect=RuntimeError("boom"))
    @patch.object(SecretRemoverAgent, "_find_latest_results")
    def test_run_handles_repo_error(self, mock_find, _mock_process):
        mock_find.return_value = {
            "repositories_with_findings": [
                {
                    "repository": "owner/repo1",
                    "findings": [{"rule_id": "r1"}],
                    "default_branch": "main",
                },
            ]
        }

        result = self.agent.run()

        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["error"], "boom")

    @patch.object(SecretRemoverAgent, "_build_redacted_context", return_value="> 1: token = <redacted>")
    @patch.object(SecretRemoverAgent, "_create_allowlist_session")
    @patch.object(SecretRemoverAgent, "_create_removal_session")
    @patch("src.agents.secret_remover.agent.analyze_finding")
    @patch("src.agents.secret_remover.agent.subprocess.run")
    @patch("src.agents.secret_remover.agent.os.getenv", return_value="fake-token")
    def test_process_repo_all_ignore(
        self,
        _mock_env,
        mock_subprocess,
        mock_analyze,
        mock_remove_session,
        mock_allowlist_session,
        _mock_context,
    ):
        mock_subprocess.return_value = MagicMock(returncode=0)
        mock_analyze.return_value = {"action": "IGNORE", "reason": "test data"}
        mock_allowlist_session.return_value = {"session_id": "session123"}

        findings = [
            {"rule_id": "rule-1", "file": "test.env", "line": 1, "commit": "abc"},
            {"rule_id": "rule-2", "file": "fake.py", "line": 2, "commit": "def"},
        ]

        result = self.agent._process_repo("owner/repo", findings, "main")

        self.assertEqual(result["ignored"], 2)
        self.assertEqual(result["to_remove"], 0)
        mock_remove_session.assert_not_called()
        mock_allowlist_session.assert_called_once()
        self.assertEqual(mock_allowlist_session.call_args[0][0], "owner/repo")
        self.assertEqual(len(mock_allowlist_session.call_args[0][1]), 2)

    @patch.object(SecretRemoverAgent, "_build_redacted_context", return_value="> 4: api_key = <redacted>")
    @patch.object(SecretRemoverAgent, "_create_allowlist_session")
    @patch.object(SecretRemoverAgent, "_create_removal_session")
    @patch("src.agents.secret_remover.agent.analyze_finding")
    @patch("src.agents.secret_remover.agent.subprocess.run")
    @patch("src.agents.secret_remover.agent.os.getenv", return_value="fake-token")
    def test_process_repo_remove_from_history(
        self,
        _mock_env,
        mock_subprocess,
        mock_analyze,
        mock_remove_session,
        mock_allowlist_session,
        _mock_context,
    ):
        mock_subprocess.return_value = MagicMock(returncode=0)
        mock_analyze.return_value = {"action": "REMOVE_FROM_HISTORY", "reason": "real token"}
        mock_remove_session.return_value = {"session_id": "session456"}

        findings = [{"rule_id": "aws-key", "file": "config.py", "line": 4, "commit": "abc"}]

        result = self.agent._process_repo("owner/repo", findings, "main")

        self.assertEqual(result["to_remove"], 1)
        self.assertEqual(result["ignored"], 0)
        mock_remove_session.assert_called_once()
        mock_allowlist_session.assert_not_called()
        self.assertEqual(result["actions"][0]["status"], "SESSION_CREATED")

    @patch.object(SecretRemoverAgent, "_build_redacted_context", return_value="> 1: token = <redacted>")
    @patch.object(SecretRemoverAgent, "_create_removal_session", return_value=None)
    @patch("src.agents.secret_remover.agent.analyze_finding")
    @patch("src.agents.secret_remover.agent.subprocess.run")
    @patch("src.agents.secret_remover.agent.os.getenv", return_value="fake-token")
    def test_process_repo_removal_session_error(
        self,
        _mock_env,
        mock_subprocess,
        mock_analyze,
        _mock_remove_session,
        _mock_context,
    ):
        mock_subprocess.return_value = MagicMock(returncode=0)
        mock_analyze.return_value = {"action": "REMOVE_FROM_HISTORY", "reason": "real token"}

        result = self.agent._process_repo(
            "owner/repo",
            [{"rule_id": "aws-key", "file": "config.py", "line": 1, "commit": "abc"}],
            "main",
        )

        self.assertEqual(result["actions"][0]["status"], "ERROR")

    @patch("src.agents.secret_remover.agent.analyze_finding", return_value={"action": "IGNORE", "reason": "ok"})
    @patch.object(SecretRemoverAgent, "_find_latest_results")
    def test_run_respects_max_findings_limit(self, mock_find, _mock_analyze):
        big_findings = [
            {"rule_id": "r", "file": f"f{i}.py", "line": i, "commit": "a"}
            for i in range(200)
        ]
        repos = [
            {"repository": f"owner/repo{i}", "findings": big_findings, "default_branch": "main"}
            for i in range(5)
        ]
        mock_find.return_value = {"repositories_with_findings": repos}

        with patch.object(self.agent, "_process_repo", return_value={"ignored": 0, "to_remove": 0, "actions": []}) as mock_process:
            result = self.agent.run()

        total_findings_analysed = sum(
            len(call.args[1])
            for call in mock_process.call_args_list
        )
        from src.agents.secret_remover.agent import _MAX_FINDINGS_PER_RUN
        self.assertLessEqual(total_findings_analysed, _MAX_FINDINGS_PER_RUN)
        self.assertEqual(len(result["actions_taken"]), len(mock_process.call_args_list))

    def test_build_redacted_context_masks_long_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir)
            target_file = repo_dir / "app.env"
            target_file.write_text(
                "DEBUG=true\nAPI_KEY=supersecretvalue123456\nNAME=demo\n",
                encoding="utf-8",
            )

            context = self.agent._build_redacted_context(
                str(repo_dir),
                {"file": "app.env", "line": 2},
            )

        self.assertIn("<redacted>", context)
        self.assertNotIn("supersecretvalue123456", context)

    def test_persona(self):
        with patch.object(self.agent, "get_instructions_section", return_value="Test Persona"):
            self.assertEqual(self.agent.persona, "Test Persona")

    def test_mission(self):
        with patch.object(self.agent, "get_instructions_section", return_value="Test Mission"):
            self.assertEqual(self.agent.mission, "Test Mission")

    def test_create_allowlist_session_success(self):
        self.agent.create_jules_session = MagicMock(return_value={"id": "session123"})

        result = self.agent._create_allowlist_session(
            "repo",
            [{"rule_id": "r1", "file": "f1"}, {"rule_id": "r2", "file": "f2"}],
            "main",
        )

        self.assertEqual(result["kind"], "IGNORE")
        self.assertEqual(result["session_id"], "session123")

    def test_create_removal_session_success(self):
        self.agent.create_jules_session = MagicMock(return_value={"id": "session123"})

        result = self.agent._create_removal_session(
            "repo",
            {"file": "f1", "_reason": "real key", "redacted_context": "> 1: KEY=<redacted>"},
            "main",
        )

        self.assertEqual(result["kind"], "REMOVE")
        self.assertEqual(result["session_id"], "session123")

    def test_create_allowlist_session_exception(self):
        self.agent.create_jules_session = MagicMock(side_effect=Exception("API Error"))
        result = self.agent._create_allowlist_session("repo", [{"rule_id": "r1", "file": "f1"}], "main")
        self.assertIsNone(result)

    def test_create_removal_session_exception(self):
        self.agent.create_jules_session = MagicMock(side_effect=Exception("API Error"))
        result = self.agent._create_removal_session("repo", {"file": "f1"}, "main")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
