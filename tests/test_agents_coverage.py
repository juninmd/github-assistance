import unittest
from datetime import UTC, datetime, timedelta, timezone  # pyright: ignore[reportUnusedImport]
from unittest.mock import MagicMock, patch

from src.agents.ci_health.agent import CIHealthAgent
from src.agents.pr_sla.agent import PRSLAAgent
from src.notifications.telegram import TelegramNotifier


class TestAgentsCoverage(unittest.TestCase):
    def setUp(self):
        self.jules_client = MagicMock()
        self.github_client = MagicMock()
        self.allowlist = MagicMock()
        self.allowlist.list_repositories.return_value = ["owner/repo"]
        self.allowlist.is_allowed.return_value = True
        self.telegram = MagicMock(spec=TelegramNotifier)
        self.telegram.escape = TelegramNotifier.escape

    def test_ci_health_agent(self):
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")
        self.assertFalse(agent.uses_repository_allowlist())

        # Test escape through telegram
        self.assertEqual(agent.telegram.escape("hello_world"), "hello\\_world")
        self.assertEqual(agent.telegram.escape(None), "")

        # Test persona/mission
        with patch.object(agent, "get_instructions_section") as mock_instr:
            mock_instr.return_value = "Content"
            self.assertEqual(agent.persona, "Content")
            self.assertEqual(agent.mission, "Content")

        # Test run with failures
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        self.github_client.get_repo.return_value = mock_repo
        mock_user = MagicMock()
        mock_user.get_repos.return_value = [mock_repo]
        self.github_client.g.get_user.return_value = mock_user

        mock_run = MagicMock()
        mock_run.created_at = datetime.now(UTC)
        mock_run.conclusion = "failure"
        mock_run.name = "test-workflow"
        mock_run.head_branch = "main"
        mock_run.html_url = "http://url"

        mock_old_run = MagicMock()
        mock_old_run.created_at = datetime.now(UTC) - timedelta(hours=25)

        mock_repo.get_workflow_runs.return_value = [mock_run, mock_old_run]

        result = agent.run()
        self.assertEqual(result["count"], 1)
        self.telegram.send_message.assert_called_once()
        self.github_client.g.get_user.assert_called_with("testuser")

        # Test run with exception
        self.github_client.get_repo.side_effect = Exception("Error")
        result = agent.run()
        self.assertEqual(result["count"], 0)
        self.github_client.get_repo.side_effect = None
        self.github_client.get_repo.return_value = mock_repo




    def test_pr_sla_agent(self):
        agent = PRSLAAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")

        # Test persona/mission/escape explicit
        with patch.object(agent, "get_instructions_section") as mock_instr:
            mock_instr.return_value = "Content"
            self.assertEqual(agent.persona, "Content")
            self.assertEqual(agent.mission, "Content")
        self.assertEqual(agent.telegram.escape(None), "")

        # Test run
        mock_issue = MagicMock()
        mock_pr = MagicMock()
        mock_pr.updated_at = datetime.now(UTC) - timedelta(hours=25)
        mock_pr.created_at = datetime.now(UTC) - timedelta(hours=25)
        mock_pr.base.repo.full_name = "owner/repo"
        mock_pr.number = 1
        mock_pr.title = "Stale PR"
        mock_pr.html_url = "http://url"

        self.github_client.search_prs.return_value = [mock_issue]
        self.github_client.get_pr_from_issue.return_value = mock_pr

        result = agent.run()
        self.assertEqual(result["count"], 1)

        # Test exception
        self.github_client.get_pr_from_issue.side_effect = Exception("Error")
        result = agent.run()
        self.assertEqual(result["count"], 0)



    def test_ci_health_agent_count_break(self):
        from src.agents.ci_health.agent import CIHealthAgent
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        self.github_client.get_repo.return_value = mock_repo
        mock_user = MagicMock()
        mock_user.get_repos.return_value = [mock_repo]
        self.github_client.g.get_user.return_value = mock_user

        mock_run = MagicMock()
        mock_run.created_at = datetime.now(UTC)
        mock_run.conclusion = "failure"
        mock_run.name = "test-workflow"
        mock_run.head_branch = "main"
        mock_run.html_url = "http://url"

        mock_repo.get_workflow_runs.return_value = [mock_run] * 35
        result = agent.run()
        self.assertEqual(result["count"], 30)

    @patch("src.agents.ci_health.agent.get_ai_client")
    def test_ci_health_agent_remediate_pipeline(self, mock_get_ai):
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")

        # Test AI fallback logic for creating an issue
        mock_ai_instance = MagicMock()
        mock_ai_instance.generate.return_value = "Suggested fix for pipeline"
        mock_get_ai.return_value = mock_ai_instance

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_issue = MagicMock()
        mock_issue.number = 42
        mock_issue.html_url = "http://issue"
        mock_repo.create_issue.return_value = mock_issue

        res = agent._create_issue_for_pipeline(mock_repo, "fails")
        self.assertEqual(res["issue_number"], 42)
        mock_ai_instance.generate.assert_called_once()

        # Test Exception when creating an issue with AI
        mock_ai_instance.generate.side_effect = Exception("AI error")
        res2 = agent._create_issue_for_pipeline(mock_repo, "fails")
        self.assertEqual(res2["issue_number"], 42) # Should fallback to basic string

        # Test no AI client available
        mock_get_ai.side_effect = Exception("No AI")
        res3 = agent._create_issue_for_pipeline(mock_repo, "fails")
        self.assertEqual(res3["issue_number"], 42) # Should fallback to basic string
        mock_get_ai.side_effect = None

        # Test failure to create an issue
        mock_repo.create_issue.side_effect = Exception("Cannot create issue")
        res4 = agent._create_issue_for_pipeline(mock_repo, "fails")
        self.assertIsNone(res4)

    def test_ci_health_agent_remediate_pipeline_full(self):
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        failures = [{"name": "tests", "conclusion": "failure", "url": "http://url"}]

        with patch.object(agent, "has_recent_jules_session") as mock_has_session:
            # Case 1: Session already exists
            mock_has_session.return_value = True
            res = agent._remediate_pipeline(mock_repo, failures)
            self.assertIsNone(res)

            # Case 2: Jules session created successfully
            mock_has_session.return_value = False

            with patch.object(agent, "load_jules_instructions") as mock_load, \
                 patch.object(agent, "create_jules_session") as mock_create:

                mock_load.return_value = "Fix this"
                mock_create.return_value = {"id": "session123", "name": "Fix CI", "title": "Fix CI"}

                res2 = agent._remediate_pipeline(mock_repo, failures)
                self.assertEqual(res2["session_id"], "session123")

            # Case 3: Creating session fails, fallback to issue
            with patch.object(agent, "load_jules_instructions"), \
                 patch.object(agent, "create_jules_session") as mock_create, \
                 patch.object(agent, "_create_issue_for_pipeline") as mock_fallback:

                mock_create.side_effect = Exception("Session failed")
                mock_fallback.return_value = {"repository": "owner/repo", "issue_number": 10}

                res3 = agent._remediate_pipeline(mock_repo, failures)
                self.assertEqual(res3["issue_number"], 10)

    def test_ci_health_agent_run_full_flow(self):
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.private = False  # Ensure it tries remediation
        self.github_client.get_repo.return_value = mock_repo

        mock_user = MagicMock()
        mock_user.get_repos.return_value = [mock_repo]
        self.github_client.g.get_user.return_value = mock_user

        mock_run = MagicMock()
        mock_run.created_at = datetime.now(UTC)
        mock_run.conclusion = "failure"
        mock_run.name = "test-workflow"
        mock_run.head_branch = "main"
        mock_run.html_url = "http://url"
        mock_repo.get_workflow_runs.return_value = [mock_run]

        with patch.object(agent, "_remediate_pipeline") as mock_remediate:
            # First loop with successful remediation returning session
            mock_remediate.return_value = {"repository": "owner/repo", "session_id": "sesh123"}
            res = agent.run()
            self.assertEqual(len(res["fix_actions"]), 1)

            # Second loop with successful remediation returning issue
            mock_remediate.return_value = {"repository": "owner/repo", "issue_url": "http://issue"}
            res2 = agent.run()
            self.assertEqual(len(res2["fix_actions"]), 1)

            # Third loop with remediation failure
            mock_remediate.side_effect = Exception("Remediation error")
            res3 = agent.run()
            self.assertEqual(len(res3["fix_actions"]), 0)

            # Fourth loop with generic action (no session_id or issue_url)
            mock_remediate.side_effect = None
            mock_remediate.return_value = {"repository": "owner/repo"}
            res4 = agent.run()
            self.assertEqual(len(res4["fix_actions"]), 1)

        # Test line 111 (no failures in dict entry) via the refactored _process_repo_entry
        agent = CIHealthAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram, target_owner="testuser")

        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.private = False

        # Call it directly to hit the defensive "if not entry.get('failures'): return None" code path
        res5 = agent._process_repo_entry("owner/repo", {"repo": mock_repo, "failures": []})
        self.assertIsNone(res5)

    def test_metrics_agent_increment(self):
        from src.agents.metrics import AgentMetrics
        metrics = AgentMetrics("test")

        # Test line 92: string conversion
        class CustomObj:
            def __str__(self):
                return "custom_error"
        metrics.add_error(str(CustomObj()))
        self.assertEqual(metrics.metrics["errors"][0]["message"], "custom_error")

        # Test line 92 summary generation with warnings
        metrics.add_warning("some_warning")
        summary = metrics.get_summary()
        self.assertIn("Warnings:", summary)

    def test_orchestration_run_agent(self):
        from src.agents.orchestration import AgentOrchestrator
        orch = AgentOrchestrator()

        # Test line 70-71: Exception block in execution (simulate by testing get_execution_order with bad deps)
        orch.register_agent("a", depends_on=["b"])
        orch.register_agent("b", depends_on=["a"])
        # Circular dependency
        order = orch.get_execution_order(["a", "b"])
        self.assertEqual(len(order), 2)

        batches = orch.get_parallel_batches(["a", "b"])
        self.assertEqual(len(batches), 1)

    def test_orchestration_main(self):
        pass # removed test because no main function in orchestration

    def test_secret_remover_find_latest_results(self):
        from src.agents.secret_remover.agent import SecretRemoverAgent
        from unittest.mock import mock_open
        agent = SecretRemoverAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram)

        with patch("os.getenv") as mock_getenv, \
             patch("glob.glob") as mock_glob, \
             patch("src.agents.secret_remover.agent.open", mock_open(read_data="{}")), \
             patch("json.load") as mock_json_load:

            # Line 126: Test RESULTS_DIR env var
            mock_getenv.return_value = "/mock/results/dir"

            # Line 137-138: Test exception in globbing
            mock_glob.side_effect = [Exception("Glob error"), ["/mock/results/dir/scanner_results.json"], []]

            # We want to test line 149-150: data not a dict
            mock_json_load.return_value = ["not_a_dict"]

            res = agent._find_latest_results()
            self.assertIsNone(res)

    def test_secret_remover_find_latest_results_malformed(self):
        from src.agents.secret_remover.agent import SecretRemoverAgent
        from unittest.mock import mock_open
        agent = SecretRemoverAgent(self.jules_client, self.github_client, self.allowlist, telegram=self.telegram)

        with patch("os.getenv", return_value=None), \
             patch("glob.glob") as mock_glob, \
             patch("src.agents.secret_remover.agent.open", mock_open(read_data="{}")), \
             patch("json.load") as mock_json_load:

            # Give it two candidate files
            mock_glob.side_effect = [["file1.json", "file2.json"], []]

            # First file is a dict but missing 'repositories_with_findings' (Line 152-153)
            # Second file throws generic Exception (Line 157-160)
            mock_json_load.side_effect = [{"wrong_key": "val"}, Exception("Read error")]

            res = agent._find_latest_results()
            self.assertIsNone(res)
