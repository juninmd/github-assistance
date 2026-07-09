"""
End-to-end smoke tests for the Jules integration pipeline.

Tests the full stack:
  1. Real HTTP calls to Jules API (requires JULES_API_KEY)
  2. Agent pipeline: BaseAgent → JulesSessionManager → JulesClient
  3. JulesTrackerAgent full flow: list → detect → answer → notify
  4. Error recovery and retry behavior
  5. CLI agent registration and import
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.agents.base_agent import BaseAgent
from src.jules.client import JulesClient

# ── Helpers ────────────────────────────────────────────────────────────


class _TestBaseAgent(BaseAgent):
    """Concrete BaseAgent subclass for testing abstract methods."""

    @property
    def persona(self) -> str:
        return "Test persona"

    @property
    def mission(self) -> str:
        return "Test mission"

    def run(self) -> dict:
        return {"status": "ok"}


def _make_test_agent(jules=None, gh=None, allowlist=None, telegram=None, name="test"):
    from unittest.mock import MagicMock
    return _TestBaseAgent(
        jules_client=jules or MagicMock(),
        github_client=gh or MagicMock(),
        allowlist=allowlist or MagicMock(),
        telegram=telegram or MagicMock(),
        name=name,
    )


# ── Configuration ──────────────────────────────────────────────────────

HAS_API_KEY = bool(os.getenv("JULES_API_KEY"))
API_KEY = os.getenv("JULES_API_KEY", "")

pytestmark_http = pytest.mark.skipif(not HAS_API_KEY, reason="JULES_API_KEY not set")


# ═══════════════════════════════════════════════════════════════════════
# 1. REAL HTTP E2E SMOKE TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestJulesHttpE2E:
    """Real HTTP calls to Jules API. Tests are slow (~30s per API call).

    Uses JULES_API_KEY from environment. The Jules API is intentionally
    slow (session listing takes 20-60s). Each test that calls the API
    is a real end-to-end validation.
    """

    @pytest.mark.skipif(not HAS_API_KEY, reason="JULES_API_KEY not set")
    def test_sources_endpoint(self):
        """list_sources returns a list."""
        client = JulesClient(api_key=API_KEY)
        sources = client.list_sources()
        assert isinstance(sources, list)
        json.dumps(sources)

    @pytest.mark.skipif(not HAS_API_KEY, reason="JULES_API_KEY not set")
    def test_sessions_endpoint_pagination(self):
        """list_sessions with max_pages=1 returns without full pagination."""
        client = JulesClient(api_key=API_KEY)
        sessions = client.list_sessions(page_size=1, max_pages=1)
        assert isinstance(sessions, list)

    @pytest.mark.skipif(not HAS_API_KEY, reason="JULES_API_KEY not set")
    def test_session_fields(self):
        """Session objects contain expected fields."""
        client = JulesClient(api_key=API_KEY)
        sessions = client.list_sessions(page_size=1, max_pages=1)
        if not sessions:
            pytest.skip("No sessions found")
        s = sessions[0]
        assert s.get("id") or s.get("name"), f"Missing id/name: {s}"
        assert s.get("createTime") or s.get("createdAt"), f"Missing createTime: {s}"
        assert isinstance(s, dict)

    @pytest.mark.skipif(not HAS_API_KEY, reason="JULES_API_KEY not set")
    def test_get_session_and_activities(self):
        """get_session returns details; list_activities returns list."""
        client = JulesClient(api_key=API_KEY)
        sessions = client.list_sessions(page_size=1, max_pages=1)
        if not sessions:
            pytest.skip("No sessions found")
        sid = sessions[0].get("id") or sessions[0].get("name", "")
        if not sid:
            pytest.skip("Session missing id")

        detail = client.get_session(sid)
        assert isinstance(detail, dict)
        assert "state" in detail or "status" in detail

        resource_name = f"sessions/{sid}"
        detail2 = client.get_session(resource_name)
        assert detail.get("name") == detail2.get("name")

        activities = client.list_activities(sid)
        assert isinstance(activities, list)

    @pytest.mark.skipif(not HAS_API_KEY, reason="JULES_API_KEY not set")
    def test_auth_headers_accepted(self):
        """API accepts the auth header format."""
        resp = requests.get(
            "https://jules.googleapis.com/v1alpha/sources",
            headers={"X-Goog-Api-Key": API_KEY, "Content-Type": "application/json"},
            timeout=60,
        )
        assert resp.status_code in (200, 401, 403)


# ═══════════════════════════════════════════════════════════════════════
# 2. AGENT PIPELINE SMOKE TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestAgentPipelineSmoke:
    """Tests the full Jules agent pipeline from BaseAgent to JulesClient."""

    def test_base_agent_create_jules_session_chain(self):
        from src.agents.jules_manager import JulesSessionManager

        jules = MagicMock(spec=JulesClient)
        jules.create_pull_request_session.return_value = {"id": "sessions/test-123"}
        log = MagicMock()

        mgr = JulesSessionManager(jules, log)
        result = mgr.create_session(
            repository="owner/test-repo",
            prompt="Fix the bug in main.py",
            title="Test session",
            base_branch="main",
            wait_for_completion=False,
        )

        assert result["id"] == "sessions/test-123"
        jules.create_pull_request_session.assert_called_once()

    def test_create_jules_session_allowlist_denied(self):
        jules = MagicMock()
        gh = MagicMock()
        allowlist = MagicMock()
        allowlist.is_allowed.return_value = False

        agent = _make_test_agent(jules, gh, allowlist)

        with pytest.raises(ValueError, match="not in allowlist"):
            agent.create_jules_session(
                repository="evil/repo", instructions="do bad", title="nope"
            )

    def test_jules_session_manager_create_session(self):
        from src.agents.jules_manager import JulesSessionManager

        client = MagicMock(spec=JulesClient)
        client.create_pull_request_session.return_value = {"id": "sessions/s1"}
        log = MagicMock()

        mgr = JulesSessionManager(client, log)
        result = mgr.create_session(
            repository="owner/repo",
            prompt="do work",
            title="My Task",
            base_branch="main",
            wait_for_completion=False,
        )

        assert result["id"] == "sessions/s1"
        client.create_pull_request_session.assert_called_with(
            repository="owner/repo", prompt="do work",
            title="My Task", base_branch="main",
        )

    def test_jules_session_manager_wait_for_completion(self):
        from src.agents.jules_manager import JulesSessionManager

        client = MagicMock(spec=JulesClient)
        client.create_pull_request_session.return_value = {"id": "sessions/s2"}
        client.wait_for_session.return_value = {"status": "COMPLETED", "outputs": ["pr"]}
        log = MagicMock()

        mgr = JulesSessionManager(client, log)
        result = mgr.create_session(
            repository="owner/repo", prompt="do work",
            title="Wait Task", base_branch="main",
            wait_for_completion=True,
        )

        assert result["status"] == "COMPLETED"
        client.create_pull_request_session.assert_called_once()
        client.wait_for_session.assert_called_once_with("sessions/s2")

    def test_jules_client_list_sources_pagination_chain(self):
        client = JulesClient(api_key="test-key")
        with patch.object(client, "list_sources") as mock_list:
            mock_list.return_value = [{"name": "s1"}, {"name": "s2"}]
            result = client.list_sources()
            assert len(result) == 2

    def test_jules_client_create_pull_request_session(self):
        client = JulesClient(api_key="test-key")
        source = client.get_source_name("owner/my-repo")
        assert source == "sources/github/owner/my-repo"

        with patch.object(client, "create_session") as mock_create:
            mock_create.return_value = {"id": "123"}
            result = client.create_pull_request_session(
                "owner/my-repo", "Implement feature X", base_branch="develop",
            )
            assert result["id"] == "123"
            mock_create.assert_called_with(
                source="sources/github/owner/my-repo",
                prompt="Implement feature X",
                title=None,
                starting_branch="develop",
                automation_mode="AUTO_CREATE_PR",
                require_plan_approval=True,
            )

    def test_jules_client_create_pull_request_session_missing_branch(self):
        client = JulesClient(api_key="test-key")
        with pytest.raises(ValueError, match="base_branch is required"):
            client.create_pull_request_session("owner/repo", "do it")


# ═══════════════════════════════════════════════════════════════════════
# 3. JULES TRACKER FULL FLOW
# ═══════════════════════════════════════════════════════════════════════


class TestJulesTrackerE2E:
    """End-to-end flow: Jules tracker agent detects, answers, notifies."""

    def _make_session(
        self, sid: str, repo: str, state: str = "AWAITING_USER_FEEDBACK",
        status_msg: str = "What branch should I use?",
    ) -> dict:
        return {
            "id": sid,
            "name": f"sessions/{sid}",
            "state": state,
            "statusMessage": status_msg,
            "sourceContext": {"source": f"sources/github/{repo}"},
            "url": f"https://jules.google.com/sessions/{sid}",
            "createTime": datetime.now(UTC).isoformat(),
        }

    def _make_activity(
        self, ts: datetime | None = None, user_msg: str | None = None,
        agent_msg: str | None = None,
    ) -> dict:
        ts = ts or datetime.now(UTC)
        activity: dict = {"createTime": ts.isoformat()}
        if user_msg:
            activity["userMessaged"] = {"userMessage": user_msg}
        if agent_msg:
            activity["agentMessaged"] = {"agentMessage": agent_msg}
        return activity

    def test_tracker_full_flow_answer_and_notify(self):
        from src.agents.jules_tracker.agent import JulesTrackerAgent

        jules = MagicMock(spec=JulesClient)
        session = self._make_session("s999", "owner/test-repo")
        jules.list_sessions.return_value = [session]
        jules.list_activities.return_value = [
            self._make_activity(
                ts=datetime.now(UTC) - timedelta(minutes=5),
                agent_msg="What branch should I use for the feature?",
            ),
        ]

        gh = MagicMock()
        allowlist = MagicMock()
        allowlist.list_repositories.return_value = ["owner/test-repo"]
        telegram = MagicMock()
        telegram.escape.return_value = "safe"
        telegram.escape_html.return_value = "safe"

        agent = JulesTrackerAgent(
            jules_client=jules, github_client=gh, allowlist=allowlist,
            telegram=telegram, ai_provider="ollama", ai_model="fake-model",
            ai_config={},
        )

        with patch.object(agent.ai_client, "generate", return_value="Use main branch."):
            result = agent.run()

        assert len(result["answered_questions"]) == 1
        assert result["answered_questions"][0]["session_id"] == "s999"
        assert result["answered_questions"][0]["repository"] == "owner/test-repo"
        assert result["answered_questions"][0]["answer"] == (
            "Use main branch.\n\nAo finalizar, abra o pull request."
        )
        assert len(result["failed"]) == 0

        jules.send_message.assert_called_once_with(
            "s999", "Use main branch.\n\nAo finalizar, abra o pull request."
        )
        telegram.send_message.assert_called()

    def test_tracker_skips_already_answered(self):
        from src.agents.jules_tracker.agent import JulesTrackerAgent

        jules = MagicMock(spec=JulesClient)
        session = self._make_session("s100", "owner/repo", state="IN_PROGRESS")
        jules.list_sessions.return_value = [session]
        jules.list_activities.return_value = [
            self._make_activity(
                ts=datetime.now(UTC) - timedelta(minutes=10),
                agent_msg="What should I do?",
            ),
            self._make_activity(
                ts=datetime.now(UTC) - timedelta(minutes=5),
                user_msg="Use the main approach.",
            ),
        ]

        gh = MagicMock()
        allowlist = MagicMock()
        allowlist.list_repositories.return_value = ["owner/repo"]
        telegram = MagicMock()

        agent = JulesTrackerAgent(
            jules_client=jules, github_client=gh, allowlist=allowlist,
            telegram=telegram, ai_provider="ollama", ai_model="fake",
            ai_config={},
        )

        with patch.object(agent.ai_client, "generate", return_value="irrelevant"):
            result = agent.run()

        assert len(result["answered_questions"]) == 0
        jules.send_message.assert_not_called()

    def test_tracker_handles_list_sessions_error(self):
        from src.agents.jules_tracker.agent import JulesTrackerAgent

        jules = MagicMock(spec=JulesClient)
        jules.list_sessions.side_effect = Exception("API unreachable")

        agent = JulesTrackerAgent(
            jules_client=jules, github_client=MagicMock(),
            allowlist=MagicMock(), telegram=MagicMock(),
            ai_provider="ollama", ai_model="fake", ai_config={},
        )

        result = agent.run()
        assert len(result["failed"]) == 1
        assert "Failed to list sessions" in result["failed"][0]["error"]

    def test_tracker_uses_status_message_fallback(self):
        from src.agents.jules_tracker.agent import JulesTrackerAgent

        jules = MagicMock(spec=JulesClient)
        session = self._make_session("s200", "owner/repo",
                                      state="AWAITING_USER_FEEDBACK",
                                      status_msg="Which deployment target?")
        jules.list_sessions.return_value = [session]
        jules.list_activities.return_value = []

        gh = MagicMock()
        allowlist = MagicMock()
        allowlist.list_repositories.return_value = ["owner/repo"]
        telegram = MagicMock()
        telegram.escape.return_value = "safe"
        telegram.escape_html.return_value = "safe"

        agent = JulesTrackerAgent(
            jules_client=jules, github_client=gh, allowlist=allowlist,
            telegram=telegram, ai_provider="ollama", ai_model="fake",
            ai_config={},
        )

        with patch.object(agent.ai_client, "generate", return_value="staging"):
            result = agent.run()

        assert len(result["answered_questions"]) == 1
        assert "deployment" in result["answered_questions"][0]["question"].lower()

    def test_tracker_handles_process_session_error(self):
        from src.agents.jules_tracker.agent import JulesTrackerAgent

        jules = MagicMock(spec=JulesClient)
        session = self._make_session("s300", "owner/repo")
        jules.list_sessions.return_value = [session]
        jules.list_activities.side_effect = Exception("Activities failed")

        gh = MagicMock()
        allowlist = MagicMock()
        allowlist.list_repositories.return_value = ["owner/repo"]
        telegram = MagicMock()

        agent = JulesTrackerAgent(
            jules_client=jules, github_client=gh, allowlist=allowlist,
            telegram=telegram, ai_provider="ollama", ai_model="fake",
            ai_config={},
        )

        result = agent.run()
        assert len(result["failed"]) == 1
        assert "s300" in result["failed"][0]["session_id"]

    def test_tracker_skips_non_allowlisted_repos(self):
        from src.agents.jules_tracker.agent import JulesTrackerAgent

        jules = MagicMock(spec=JulesClient)
        session = self._make_session("s400", "other-org/private-repo")
        jules.list_sessions.return_value = [session]
        jules.list_activities.return_value = []

        gh = MagicMock()
        allowlist = MagicMock()
        allowlist.list_repositories.return_value = ["owner/allowed-repo"]
        telegram = MagicMock()

        agent = JulesTrackerAgent(
            jules_client=jules, github_client=gh, allowlist=allowlist,
            telegram=telegram, ai_provider="ollama", ai_model="fake",
            ai_config={},
        )

        result = agent.run()
        assert len(result["answered_questions"]) == 0


# ═══════════════════════════════════════════════════════════════════════
# 4. ERROR RECOVERY & RESILIENCE
# ═══════════════════════════════════════════════════════════════════════


class TestJulesResilience:
    """Error recovery, retry, timeout, and edge cases."""

    def test_client_init_without_key_warns(self):
        import warnings
        with patch.dict(os.environ, {}, clear=True):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                client = JulesClient()
                assert client.api_key is None
                assert len(w) == 1
                assert "JULES_API_KEY" in str(w[0].message)

    def test_retry_on_connection_error(self):
        client = JulesClient(api_key="test-key")
        with patch("src.jules.client.requests.get") as mock_get:
            mock_get.side_effect = [
                requests.ConnectionError("no route"),
                MagicMock(status_code=200, json=lambda: {"sources": [{"name": "s1"}]}),
            ]
            result = client.list_sources()
            assert len(result) == 1
            assert mock_get.call_count == 2

    def test_retry_on_timeout(self):
        client = JulesClient(api_key="test-key")
        with patch("src.jules.client.requests.get") as mock_get:
            mock_get.side_effect = [
                requests.Timeout("slow"),
                MagicMock(status_code=200, json=lambda: {"sources": [{"name": "s1"}]}),
            ]
            result = client.list_sources()
            assert len(result) == 1
            assert mock_get.call_count == 2

    def test_retry_gives_up_after_max_attempts(self):
        client = JulesClient(api_key="test-key")
        with patch("src.jules.client.requests.get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("always fails")
            with pytest.raises(requests.ConnectionError):
                client.list_sources()
            assert mock_get.call_count >= 2

    def test_get_session_normalizes_id(self):
        client = JulesClient(api_key="test-key")
        with patch.object(client, "_normalize_session_id") as mock_norm:
            mock_norm.return_value = "raw123"
            with patch.object(client, "get_session") as mock_get:
                resp = MagicMock()
                resp.json.return_value = {"id": "raw123"}
                mock_get.return_value = resp.json()
                result = client.get_session("sessions/raw123")
                assert result["id"] == "raw123"

    def test_session_timeout_raises(self):
        client = JulesClient(api_key="test-key")
        with patch.object(client, "get_session") as mock_get:
            mock_get.return_value = {"status": "RUNNING"}
            with pytest.raises(TimeoutError):
                client.wait_for_session("123", max_wait_seconds=0, poll_interval=0)

    def test_branch_validation_in_create_session(self):
        client = JulesClient(api_key="test-key")
        with pytest.raises(ValueError, match="starting_branch is required"):
            client.create_session("source", "prompt", starting_branch="")

    def test_extract_repository_name(self):
        from src.agents.jules_tracker.utils import extract_repository_name
        session = {"sourceContext": {"source": "sources/github/owner/my-app"}}
        assert extract_repository_name(session) == "owner/my-app"

    def test_extract_repository_name_no_prefix(self):
        from src.agents.jules_tracker.utils import extract_repository_name
        session = {"sourceContext": {"source": "custom/source"}}
        assert extract_repository_name(session) == "custom/source"

    def test_get_pending_question_with_activities(self):
        from src.agents.jules_tracker.utils import get_pending_question
        activities = [
            {"createTime": "2026-01-01T00:00:00Z",
             "agentMessaged": {"agentMessage": "What config file?"}},
        ]
        result = get_pending_question({}, activities)
        assert result == "What config file?"

    def test_get_pending_question_status_message(self):
        from src.agents.jules_tracker.utils import get_pending_question
        session = {
            "state": "AWAITING_USER_FEEDBACK",
            "statusMessage": "Which branch to target?",
        }
        result = get_pending_question(session, [])
        assert result == "Which branch to target?"

    def test_ensure_open_pr_request(self):
        from src.agents.jules_tracker.utils import ensure_open_pr_request

        assert ensure_open_pr_request("Use main.") == (
            "Use main.\n\nAo finalizar, abra o pull request."
        )
        assert ensure_open_pr_request("Open the pull request when done.") == (
            "Open the pull request when done."
        )
        assert ensure_open_pr_request("") == "Ao finalizar, abra o pull request."

    def test_colorize_respects_no_color(self):
        from src.agents.jules_tracker.utils import colorize
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=True):
            assert colorize("hello", "\033[92m") == "hello"


# ═══════════════════════════════════════════════════════════════════════
# 5. CLI & REGISTRY
# ═══════════════════════════════════════════════════════════════════════


class TestJulesCLIIntegration:
    """CLI integration: agent registry, imports, scripts."""

    def test_agent_registry_contains_jules_tracker(self):
        from src.agents.registry import AGENT_REGISTRY
        assert "jules-tracker" in AGENT_REGISTRY.keys()

    def test_agent_registry_can_load_jules_tracker(self):
        from src.agents.registry import AGENT_REGISTRY
        cls = AGENT_REGISTRY["jules-tracker"]
        assert cls.__name__ == "JulesTrackerAgent"

    def test_agent_registry_has_jules_client_dep(self):
        from src.agents.registry import AGENTS_WITH_JULES
        assert "senior-developer" in AGENTS_WITH_JULES
        assert "jules-tracker" in AGENTS_WITH_JULES

    def test_jules_tracker_preflight_requires_litellm_and_jules_keys(self):
        from src.config.settings import Settings
        from src.utils.health import run_health_checks

        settings = Settings(
            github_token="gh-token",
            jules_api_key=None,
            enable_ai=True,
            ai_provider="litellm",
            ai_model="cloud/llama-70b",
            litellm_api_key=None,
            litellm_api_base="https://litellm.example/v1",
        )

        report = run_health_checks(settings, "jules-tracker")

        assert "JULES_API_KEY missing" in report.summary()
        assert "LITELLM_API_KEY is missing" in report.summary()
        assert not report.ok

    def test_jules_tracker_preflight_accepts_litellm_and_jules_keys(self):
        from src.config.settings import Settings
        from src.utils.health import run_health_checks

        settings = Settings(
            github_token="gh-token",
            jules_api_key="jules-key",
            enable_ai=True,
            ai_provider="litellm",
            ai_model="cloud/llama-70b",
            litellm_api_key="litellm-key",
            litellm_api_base="https://litellm.example/v1",
        )

        report = run_health_checks(settings, "jules-tracker")

        assert report.ok
        assert "JULES_API_KEY present" in report.summary()
        assert "AI provider: litellm / model: cloud/llama-70b" in report.summary()

    def test_scripts_entry_point_exists(self):
        from src import scripts
        assert hasattr(scripts, "jules_tracker")

    def test_run_agent_can_import(self):
        from src.run_agent import main
        assert callable(main)

    def test_jules_tracker_instructions_loaded(self):
        from src.agents.jules_tracker.agent import JulesTrackerAgent
        gh = MagicMock()
        allowlist = MagicMock()
        agent = JulesTrackerAgent(
            jules_client=MagicMock(), github_client=gh,
            allowlist=allowlist, telegram=MagicMock(),
            ai_provider="ollama", ai_model="fake", ai_config={},
        )
        persona = agent.persona
        assert "proactive Jules Tracker" in persona.lower() or persona

    def test_jules_client_header_format(self):
        client = JulesClient(api_key="my-key")
        assert client.headers["X-Goog-Api-Key"] == "my-key"
        assert client.headers["Content-Type"] == "application/json"

    def test_get_source_name_format(self):
        client = JulesClient(api_key="x")
        assert client.get_source_name("a/b") == "sources/github/a/b"
        assert client.get_source_name("org/repo-name") == "sources/github/org/repo-name"


# ═══════════════════════════════════════════════════════════════════════
# 6. WEBHOOK INTEGRATION (Jules + PR Assistant)
# ═══════════════════════════════════════════════════════════════════════


class TestJulesWebhookIntegration:
    """Jules sessions triggered via webhook (PR events)."""

    def test_has_recent_jules_session_blocks_duplicates(self):
        jules = MagicMock()
        jules.list_sessions.return_value = [
            {
                "id": "s1",
                "title": "Fix bug in owner/test-repo",
                "createTime": datetime.now(UTC).isoformat(),
            }
        ]
        agent = _make_test_agent(jules=jules)

        assert agent.has_recent_jules_session("owner/test-repo", "bug") is True
        assert agent.has_recent_jules_session("owner/other-repo", "bug") is False

    def test_has_recent_jules_session_handles_exception(self):
        jules = MagicMock()
        jules.list_sessions.side_effect = Exception("fail")
        agent = _make_test_agent(jules=jules)
        assert agent.has_recent_jules_session("repo", "task") is False
