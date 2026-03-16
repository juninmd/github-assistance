"""Tests for the Secret Remover Agent."""
import unittest
from unittest.mock import MagicMock, mock_open, patch

from src.agents.secret_remover.agent import SecretRemoverAgent
from src.agents.secret_remover.ai_analyzer import _parse_ai_response, analyze_finding

# ---------------------------------------------------------------------------
# AI Analyzer unit tests
# ---------------------------------------------------------------------------

class TestParseAIResponse(unittest.TestCase):
    def test_valid_remove_from_history(self):
        raw = '{"action": "REMOVE_FROM_HISTORY", "reason": "real API key"}'
        result = _parse_ai_response(raw)
        self.assertEqual(result["action"], "REMOVE_FROM_HISTORY")
        self.assertEqual(result["reason"], "real API key")

    def test_valid_ignore(self):
        raw = '{"action": "IGNORE", "reason": "test fixture"}'
        result = _parse_ai_response(raw)
        self.assertEqual(result["action"], "IGNORE")

    def test_strips_markdown_fences(self):
        raw = '```json\n{"action": "IGNORE", "reason": "fake"}\n```'
        result = _parse_ai_response(raw)
        self.assertEqual(result["action"], "IGNORE")

    def test_invalid_json_falls_back(self):
        result = _parse_ai_response("not json at all")
        self.assertEqual(result["action"], "IGNORE")
        self.assertIn("parse", result["reason"].lower())

    def test_unknown_action_falls_back(self):
        result = _parse_ai_response('{"action": "UNKNOWN", "reason": "?"}')
        self.assertEqual(result["action"], "IGNORE")


class TestAnalyzeFinding(unittest.TestCase):
    def test_returns_ai_decision(self):
        ai_client = MagicMock()
        ai_client.generate.return_value = '{"action": "IGNORE", "reason": "test value"}'
        finding = {"rule_id": "generic-api-key", "description": "API Key", "file": "test.env", "line": 1, "commit": "abc", "date": "2024-01-01"}
        result = analyze_finding(finding, ai_client)
        self.assertEqual(result["action"], "IGNORE")

    def test_ai_exception_returns_ignore(self):
        ai_client = MagicMock()
        ai_client.generate.side_effect = RuntimeError("network error")
        finding = {"rule_id": "aws-key", "description": "", "file": "file.py", "line": 5, "commit": "", "date": ""}
        result = analyze_finding(finding, ai_client)
        self.assertEqual(result["action"], "IGNORE")
        self.assertIn("AI analysis failed", result["reason"])


# ---------------------------------------------------------------------------
# Agent-level tests
# ---------------------------------------------------------------------------

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

    # ---- _find_latest_results ------------------------------------------

    @patch("glob.glob")
    def test_find_latest_results_no_files(self, mock_glob):
        mock_glob.return_value = []
        self.assertIsNone(self.agent._find_latest_results())

    @patch("builtins.open", mock_open(read_data='{"repositories_with_findings": []}'))
    @patch("glob.glob")
    def test_find_latest_results_returns_latest(self, mock_glob):
        mock_glob.return_value = ["results/security-scanner_20260101.json", "results/security-scanner_20260201.json"]
        result = self.agent._find_latest_results()
        self.assertIsNotNone(result)
        self.assertIn("repositories_with_findings", result or {})

    @patch("builtins.open", mock_open(read_data='{"repositories_with_findings": []}'))
    @patch("glob.glob")
    def test_find_latest_results_searches_repo_root_when_cwd_has_none(self, mock_glob):
        # Simulate cwd search returning nothing, but repo-root search returning a file
        mock_glob.side_effect = [[], ["results/security-scanner_20260201.json"]]
        result = self.agent._find_latest_results()
        self.assertIsNotNone(result)
        self.assertIn("repositories_with_findings", result or {})
        self.assertEqual(mock_glob.call_count, 2)

    @patch("builtins.open", mock_open(read_data='not json'))
    @patch("glob.glob")
    def test_find_latest_results_skips_malformed_json(self, mock_glob):
        # Two files: first is malformed, second is good.
        mock_glob.return_value = ["results/security-scanner_20260301.json", "results/security-scanner_20260302.json"]

        # open() will be called twice; first time malformed, second time valid
        m = mock_open()
        m.side_effect = [mock_open(read_data='not json').return_value, mock_open(read_data='{"repositories_with_findings": []}').return_value]
        with patch("builtins.open", m):
            result = self.agent._find_latest_results()
        self.assertIsNotNone(result)
        self.assertIn("repositories_with_findings", result or {})

    # ---- run: no results -----------------------------------------------

    @patch.object(SecretRemoverAgent, "_find_latest_results", return_value=None)
    def test_run_no_results_sends_error(self, _mock_find):
        result = self.agent.run()
        self.assertIn("error", result)
        self.telegram.send_message.assert_called_once()
        msg = self.telegram.send_message.call_args[0][0]
        self.assertIn("Secret Remover", msg)

    # ---- run: normal flow ----------------------------------------------

    @patch.object(SecretRemoverAgent, "_process_repo")
    @patch.object(SecretRemoverAgent, "_find_latest_results")
    def test_run_processes_repos(self, mock_find, mock_process):
        mock_find.return_value = {
            "repositories_with_findings": [
                {"repository": "owner/repo1", "findings": [{"rule_id": "r1"}], "default_branch": "main"},
                {"repository": "owner/repo2", "findings": [{"rule_id": "r2"}], "default_branch": "master"},
            ]
        }
        mock_process.return_value = {"repository": "owner/repo1", "ignored": 1, "to_remove": 0, "sessions": []}
        result = self.agent.run()
        self.assertEqual(result["total_repos_processed"], 2)
        self.assertEqual(mock_process.call_count, 2)

    @patch.object(SecretRemoverAgent, "_process_repo", side_effect=RuntimeError("boom"))
    @patch.object(SecretRemoverAgent, "_find_latest_results")
    def test_run_handles_repo_error(self, mock_find, _mock_process):
        mock_find.return_value = {
            "repositories_with_findings": [
                {"repository": "owner/repo1", "findings": [{"rule_id": "r1"}], "default_branch": "main"},
            ]
        }
        result = self.agent.run()
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["error"], "boom")

    # ---- _process_repo -------------------------------------------------

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data="secret=123\n")
    @patch("subprocess.run")
    @patch("src.agents.secret_remover.agent.analyze_finding")
    @patch("os.getenv", return_value="fake-token")
    def test_process_repo_all_ignore(self, mock_env, mock_analyze, mock_sub, mock_file, mock_exists):
        mock_analyze.return_value = {"action": "IGNORE", "reason": "test data"}
        findings = [
            {"rule_id": "rule-1", "file": "test.env", "line": 1, "commit": "abc"},
            {"rule_id": "rule-2", "file": "fake.py", "line": 2, "commit": "def"},
        ]
        result = self.agent._process_repo("owner/repo", findings, "main")
        self.assertEqual(result["ignored"], 2)
        self.assertEqual(result["to_remove"], 0)
        # Should NOT run git-filter-repo for IGNORE
        self.assertFalse(any("git-filter-repo" in str(c) for c in mock_sub.call_args_list))

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data="secret=123\n")
    @patch("subprocess.run")
    @patch("src.agents.secret_remover.agent.analyze_finding")
    @patch("os.getenv", return_value="fake-token")
    def test_process_repo_remove_from_history(self, mock_env, mock_analyze, mock_sub, mock_file, mock_exists):
        mock_analyze.return_value = {"action": "REMOVE_FROM_HISTORY", "reason": "real token"}
        # Mock git rev-parse HEAD
        mock_sub.return_value = MagicMock(stdout="new-commit-sha", returncode=0)

        findings = [{"rule_id": "aws-key", "file": "config.py", "line": 1, "commit": "abc"}]
        result = self.agent._process_repo("owner/repo", findings, "main")

        self.assertEqual(result["to_remove"], 1)
        self.assertEqual(result["ignored"], 0)

        # Verify git-filter-repo was called
        filter_calls = [c for c in mock_sub.call_args_list if "git_filter_repo" in str(c)]
        self.assertTrue(len(filter_calls) > 0)

        # Verify force push was called
        push_calls = [c for c in mock_sub.call_args_list if "push" in str(c) and "--force" in str(c)]
        self.assertTrue(len(push_calls) >= 2) # --all and --tags

    @patch("os.getenv", return_value="fake-token")
    @patch("src.agents.secret_remover.agent.analyze_finding")
    def test_process_repo_error_handling(self, mock_analyze, mock_env):
        mock_analyze.return_value = {"action": "REMOVE_FROM_HISTORY", "reason": "test"}
        # subprocess.run is not patched here, so it might fail or we can patch it to fail
        with patch("subprocess.run", side_effect=RuntimeError("git clone failed")):
            findings = [{"rule_id": "r", "file": "f.env", "line": 1, "commit": "a"}]
            # Cloning failure in _process_repo (outside the per-finding loop or inside)
            # In our implementation, clone is before the loop.
            with self.assertRaises(RuntimeError):
                self.agent._process_repo("owner/repo", findings, "main")

    # ---- max findings guard --------------------------------------------

    @patch("src.agents.secret_remover.agent.analyze_finding", return_value={"action": "IGNORE", "reason": "ok"})
    @patch.object(SecretRemoverAgent, "_find_latest_results")
    def test_run_respects_max_findings_limit(self, mock_find, _mock_analyze):
        # Create many repos with many findings to exceed _MAX_FINDINGS_PER_RUN
        big_findings = [{"rule_id": "r", "file": f"f{i}.py", "line": i, "commit": "a"} for i in range(200)]
        repos = [{"repository": f"owner/repo{i}", "findings": big_findings, "default_branch": "main"} for i in range(5)]
        mock_find.return_value = {"repositories_with_findings": repos}
        self.agent.create_jules_session = MagicMock(return_value={"id": "s"})
        result = self.agent.run()
        # Should have processed through repos up until limit is hit
        total_findings_analysed = sum(r.get("ignored", 0) + r.get("to_remove", 0) for r in result["actions_taken"])
        from src.agents.secret_remover.agent import _MAX_FINDINGS_PER_RUN
        self.assertLessEqual(total_findings_analysed, _MAX_FINDINGS_PER_RUN)



    def test_persona_final(self):
        with patch.object(self.agent, "get_instructions_section", return_value="Test Persona"):
            self.assertEqual(self.agent.persona, "Test Persona")

    def test_mission_final(self):
        with patch.object(self.agent, "get_instructions_section", return_value="Test Mission"):
            self.assertEqual(self.agent.mission, "Test Mission")

    @patch("src.agents.secret_remover.agent.os.path.exists", return_value=True)
    @patch("builtins.open")
    def test_remove_secret_locally_full_final(self, mock_open, mock_exists):
        mock_file = MagicMock()
        mock_file.readlines.return_value = ["line1\n", "secret_line\n", "line3\n"]
        mock_open.return_value.__enter__.return_value = mock_file
        with patch("src.agents.secret_remover.agent.subprocess.run") as mock_sub:
            mock_sub.return_value.stdout = "sha123"
            self.agent._remove_secret_locally("dir", "repo", {"file": "f", "line": 2, "rule_id": "r"}, "main")
            self.telegram.send_message.assert_called_once()

    @patch("src.agents.secret_remover.agent.os.path.exists", return_value=True)
    @patch("builtins.open")
    def test_remove_secret_locally_out_of_bounds_final(self, mock_open, mock_exists):
        mock_file = MagicMock()
        mock_file.readlines.return_value = ["line1\n"]
        mock_open.return_value.__enter__.return_value = mock_file
        with patch("src.agents.secret_remover.agent.subprocess.run") as mock_sub:
            mock_sub.return_value.stdout = "sha123"
            self.agent._remove_secret_locally("dir", "repo", {"file": "f", "line": 5, "rule_id": "r"}, "main")
            self.telegram.send_message.assert_called_once()

    def test_create_allowlist_session_success_final(self):
        self.agent.create_jules_session = MagicMock(return_value={"id": "session123"})
        findings = [{"rule_id": "r1", "file": "f1"}, {"rule_id": "r2", "file": "f2"}]
        result = self.agent._create_allowlist_session("repo", findings, "main")
        self.assertEqual(result["kind"], "IGNORE")
        self.assertEqual(result["session_id"], "session123")

    def test_create_removal_session_success_final(self):
        self.agent.create_jules_session = MagicMock(return_value={"id": "session123"})
        result = self.agent._create_removal_session("repo", {"file": "f1"}, "main")
        self.assertEqual(result["kind"], "REMOVE")
        self.assertEqual(result["session_id"], "session123")

    def test_create_allowlist_session_exception_final(self):
        self.agent.create_jules_session = MagicMock(side_effect=Exception("API Error"))
        result = self.agent._create_allowlist_session("repo", [{"rule_id": "r1", "file": "f1"}], "main")
        self.assertIsNone(result)

    def test_create_removal_session_exception_final(self):
        self.agent.create_jules_session = MagicMock(side_effect=Exception("API Error"))
        result = self.agent._create_removal_session("repo", {"file": "f1"}, "main")
        self.assertIsNone(result)

    def test_find_latest_results_env_dir(self):
        import json
        import os
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "security_scanner_results_test.json"), "w") as f:
                json.dump({"repositories_with_findings": {}}, f)

            with patch.dict(os.environ, {"RESULTS_DIR": td}):
                with patch("glob.glob", return_value=[os.path.join(td, "security_scanner_results_test.json")]):
                    res = self.agent._find_latest_results()
                    self.assertIsNotNone(res)

    def test_find_latest_results_invalid_format(self):
        import json
        import os
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            file_not_dict = os.path.join(td, "security_scanner_results_test1.json")
            with open(file_not_dict, "w") as f:
                json.dump(["not", "a", "dict"], f)

            file_missing_key = os.path.join(td, "security_scanner_results_test2.json")
            with open(file_missing_key, "w") as f:
                json.dump({"other_key": "val"}, f)

            file_malformed = os.path.join(td, "security_scanner_results_test3.json")
            with open(file_malformed, "w") as f:
                f.write("{ invalid json")

            with patch.dict(os.environ, {"RESULTS_DIR": td}):
                with patch("glob.glob", side_effect=[[file_not_dict, file_missing_key, file_malformed], [], []]):
                    res = self.agent._find_latest_results()
                    self.assertIsNone(res)

    def test_find_latest_results_glob_exception(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"RESULTS_DIR": "/fake/dir"}):
            with patch("glob.glob", side_effect=Exception("Glob error")):
                res = self.agent._find_latest_results()
                self.assertIsNone(res)

    def test_find_latest_results_read_exception(self):
        import json
        import os
        import tempfile
        from unittest.mock import mock_open, patch

        with tempfile.TemporaryDirectory() as td:
            fake_file = os.path.join(td, "security_scanner_results_test.json")
            with open(fake_file, "w") as f:
                json.dump({"repositories_with_findings": {}}, f)

            with patch.dict(os.environ, {"RESULTS_DIR": td}):
                with patch("glob.glob", return_value=[fake_file]):
                    with patch("builtins.open", side_effect=Exception("Open error")):
                        res = self.agent._find_latest_results()
                        self.assertIsNone(res)

    def test_remove_secret_locally_edge_cases(self):
        import os
        from unittest.mock import MagicMock, patch
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="commit123")
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open") as mock_open:
                    mock_f = MagicMock()
                    mock_f.readlines.return_value = ["line1\n", "line2\n"]
                    mock_open.return_value.__enter__.return_value = mock_f

                    self.agent._remove_secret_locally("/tmp/clone", "repo", {"file": "f.txt", "line": 5}, "main")
                    # Should handle index out of bounds gracefully

                    mock_f.readlines.side_effect = Exception("File read error")
                    self.agent._remove_secret_locally("/tmp/clone", "repo", {"file": "f.txt", "line": 1}, "main")
                    # Should handle Exception

    @patch("src.agents.secret_remover.agent.analyze_finding")
    @patch("src.agents.secret_remover.agent.os.getenv", return_value="token")
    @patch("src.agents.secret_remover.agent.subprocess.run")
    def test_process_repo_ignore_action_final(self, mock_sub, mock_getenv, mock_analyze):
        mock_analyze.return_value = {"action": "IGNORE_FALSE_POSITIVE", "reason": "reason"}
        result = self.agent._process_repo("repo", [{"file": "f", "rule_id": "r"}], "main")
        self.assertEqual(result["ignored"], 1)

    @patch("src.agents.secret_remover.agent.analyze_finding")
    @patch("src.agents.secret_remover.agent.os.getenv", return_value="token")
    @patch("src.agents.secret_remover.agent.subprocess.run")
    def test_process_repo_remove_action_error_final(self, mock_sub, mock_getenv, mock_analyze):
        mock_analyze.return_value = {"action": "REMOVE_FROM_HISTORY", "reason": "reason"}
        self.agent._remove_secret_locally = MagicMock(side_effect=Exception("Err"))
        with patch("src.agents.secret_remover.agent.tempfile.TemporaryDirectory") as mock_temp:
            mock_temp.return_value.__enter__.return_value = "dir"
            res = self.agent._process_repo("repo", [{"file": "f", "rule_id": "r"}], "main")
            self.assertEqual(res["actions"][0]["status"], "ERROR")

    @patch("src.agents.secret_remover.agent.os.path.exists", return_value=True)
    @patch("builtins.open", side_effect=Exception("Read Error"))
    @patch("src.agents.secret_remover.agent.subprocess.run")
    def test_remove_secret_locally_exception_final(self, mock_sub, mock_open, mock_exists):
        mock_sub.return_value.stdout = "sha123"
        self.agent._remove_secret_locally("dir", "repo", {"file": "f", "line": 1, "rule_id": "r"}, "main")

if __name__ == "__main__":
    unittest.main()
