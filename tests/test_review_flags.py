"""Tests for the advisory review runtime flags and reviewer enablement defaults."""

import os
from unittest.mock import patch

from src.agents.pr_assistant import llm_reviewer, opencode_reviewer, review_flags

_CLEAR = patch.dict(os.environ, {}, clear=True)


def test_review_dry_run_defaults_false():
    with _CLEAR:
        assert review_flags.review_dry_run() is False


def test_review_dry_run_true_when_enabled():
    with patch.dict(os.environ, {"REVIEW_DRY_RUN": "true"}):
        assert review_flags.review_dry_run() is True


def test_gate_min_severity_default_and_custom():
    with _CLEAR:
        assert review_flags.gate_min_severity() == "error"
    with patch.dict(os.environ, {"REVIEW_GATE_MIN_SEVERITY": "WARN"}):
        assert review_flags.gate_min_severity() == "warn"


def test_enabled_flag_defaults_and_falsey_values():
    with _CLEAR:
        assert review_flags.enabled("SOME_FLAG", True) is True
    for value in ("0", "false", "no", "off", "FALSE"):
        with patch.dict(os.environ, {"SOME_FLAG": value}):
            assert review_flags.enabled("SOME_FLAG", True) is False
    with patch.dict(os.environ, {"SOME_FLAG": "yes"}):
        assert review_flags.enabled("SOME_FLAG", False) is True


def test_llm_review_enabled_by_default_and_disabled_by_env():
    with _CLEAR:
        assert llm_reviewer.llm_review_enabled() is True
    with patch.dict(os.environ, {"LLM_REVIEW_ENABLED": "false"}):
        assert llm_reviewer.llm_review_enabled() is False


def test_opencode_review_is_opt_in():
    with _CLEAR:
        assert opencode_reviewer.opencode_review_enabled() is False
    with patch.dict(os.environ, {"OPENCODE_REVIEW_ENABLED": "true"}):
        assert opencode_reviewer.opencode_review_enabled() is True
