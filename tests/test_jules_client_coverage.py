"""Coverage tests for uncovered Jules client and utils paths."""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.agents.utils import is_same_day_utc_minus_3
from src.jules.client import JulesClient


class TestJulesClientCoverage:
    """Targeted tests for lines missed by test_jules_client.py."""

    def test_env_int_invalid_value(self):
        from src.jules.client import _env_int
        result = _env_int("NONEXISTENT_VAR_THAT_IS_SET_TO_BAD", 42)
        assert result == 42

    def test_env_int_invalid_raises_value_error(self):
        from src.jules.client import _env_int
        with patch.dict(os.environ, {"TEST_BAD_INT": "not-a-number"}, clear=True):
            result = _env_int("TEST_BAD_INT", 1800)
            assert result == 1800

    def test_env_int_large_value(self):
        from src.jules.client import _env_int
        with patch.dict(os.environ, {"TEST_LARGE_INT": "9999"}, clear=True):
            val = _env_int("TEST_LARGE_INT", 1800)
            assert val == 9999

    def test_env_int_minimum_clamp(self):
        from src.jules.client import _env_int
        with patch.dict(os.environ, {"TEST_ZERO": "0"}, clear=True):
            val = _env_int("TEST_ZERO", 10, minimum=1)
            assert val == 1

    @patch("src.jules.client.requests.get")
    def test_list_sources_pagination(self, mock_get):
        from src.jules.client import JulesClient
        client = JulesClient("key")
        mock_get.return_value.json.side_effect = [
            {"sources": ["s1"], "nextPageToken": "tok1"},
            {"sources": ["s2"]},
        ]
        result = client.list_sources()
        assert result == ["s1", "s2"]
        assert mock_get.call_count == 2

    @patch("src.jules.client.requests.get")
    def test_list_sessions_pagination(self, mock_get):
        client = JulesClient("key")
        mock_get.return_value.json.side_effect = [
            {"sessions": ["s1"], "nextPageToken": "tok1"},
            {"sessions": ["s2"]},
        ]
        result = client.list_sessions()
        assert result == ["s1", "s2"]
        assert mock_get.call_count == 2

    @patch("src.jules.client.requests.get")
    def test_list_activities_pagination(self, mock_get):
        client = JulesClient("key")
        mock_get.return_value.json.side_effect = [
            {"activities": ["a1"], "nextPageToken": "tok1"},
            {"activities": ["a2"]},
        ]
        result = client.list_activities("sessions/1")
        assert result == ["a1", "a2"]
        assert mock_get.call_count == 2

    @patch("src.jules.client.requests.post")
    def test_create_session_no_title_no_automation(self, mock_post):
        mock_post.return_value.json.return_value = {"id": "1"}
        client = JulesClient("key")
        result = client.create_session(
            "source", "prompt", title="",
            starting_branch="main", automation_mode="",
            require_plan_approval=False,
        )
        assert result["id"] == "1"
        _args, kwargs = mock_post.call_args
        assert "title" not in kwargs["json"]
        assert "automationMode" not in kwargs["json"]
        assert "requirePlanApproval" not in kwargs["json"]

    def test_create_session_missing_starting_branch(self):
        client = JulesClient("key")
        with pytest.raises(ValueError, match="starting_branch is required"):
            client.create_session("source", "prompt", title="t", starting_branch="")

    def test_get_session_with_url(self):
        client = JulesClient("key")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"name": "sessions/1", "url": "https://jules.google.com/sessions/1"}
        with patch("src.jules.client.requests.get", return_value=mock_resp):
            result = client.get_session("1")
            assert result["url"] == "https://jules.google.com/sessions/1"


class TestIsJulesRetryable:
    """Coverage for _is_jules_retryable HTTPError branches."""

    def test_retryable_on_http_error_with_retryable_status(self):
        from src.jules.client import _is_jules_retryable
        resp = MagicMock()
        resp.status_code = 429
        err = requests.HTTPError(response=resp)
        assert _is_jules_retryable(err) is True

    def test_retryable_on_http_error_with_non_retryable_status(self):
        from src.jules.client import _is_jules_retryable
        resp = MagicMock()
        resp.status_code = 400
        err = requests.HTTPError(response=resp)
        assert _is_jules_retryable(err) is False

    def test_retryable_on_connection_error(self):
        from src.jules.client import _is_jules_retryable
        assert _is_jules_retryable(requests.ConnectionError()) is True

    def test_retryable_on_timeout(self):
        from src.jules.client import _is_jules_retryable
        assert _is_jules_retryable(requests.Timeout()) is True


class TestUtilsCoverage:
    """Coverage for utils.py edge cases."""

    def test_is_same_day_utc_minus_3_none_date(self):
        session = {"createTime": "2026-01-01T00:00:00Z"}
        result = is_same_day_utc_minus_3(session, None)
        assert result is False

    def test_is_same_day_utc_minus_3_exception(self):
        session = {"createTime": "invalid-date"}
        result = is_same_day_utc_minus_3(session, datetime.now(UTC).date())
        assert result is False

    def test_is_same_day_utc_minus_3_matching(self):
        dt = datetime.now(UTC)
        session = {"createTime": dt.isoformat()}
        target = (dt.astimezone(UTC) - timedelta(hours=3)).date()
        result = is_same_day_utc_minus_3(session, target)
        assert result is True

    def test_build_pr_body(self):
        from src.agents.utils import build_pr_body
        body = build_pr_body("test-agent", "My Title", "output text", "free-model")
        assert "test-agent" in body
        assert "My Title" in body
        assert "free-model" in body
        assert "output text" in body

    @patch.dict(os.environ, {}, clear=True)
    def test_load_instructions_not_found_no_logger(self):
        from src.agents.utils import load_instructions
        result = load_instructions("non_existent_agent_xyz")
        assert result == ""

    @patch.dict(os.environ, {}, clear=True)
    def test_load_jules_instructions_not_found(self):
        from src.agents.utils import load_jules_instructions
        result = load_jules_instructions("non_existent_agent_xyz", "nonexistent.md")
        assert result == ""

    def test_check_rate_limit_exception(self):
        from src.agents.utils import check_github_rate_limit
        client = MagicMock()
        client.g.get_rate_limit.side_effect = Exception("API error")
        result = check_github_rate_limit(client)
        assert result == -1

    def test_get_instructions_section_empty(self):
        from src.agents.utils import get_instructions_section
        result = get_instructions_section("", "## Header")
        assert result == ""
