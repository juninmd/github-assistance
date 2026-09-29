"""Tests for the opencode review enable flag and idempotency marker."""

from unittest.mock import MagicMock

from src.agents.pr_assistant.opencode_reviewer import (
    has_existing_opencode_review_comment,
    opencode_review_enabled,
)
from src.agents.pr_assistant.review_verdict import REVIEW_MARKER


def test_opencode_review_disabled_by_default(monkeypatch):
    monkeypatch.delenv("OPENCODE_REVIEW_ENABLED", raising=False)
    assert opencode_review_enabled() is False


def test_opencode_review_enabled_by_env(monkeypatch):
    monkeypatch.setenv("OPENCODE_REVIEW_ENABLED", "1")
    assert opencode_review_enabled() is True


def test_has_existing_comment_true():
    pr = MagicMock()
    comment = MagicMock()
    comment.body = f"texto {REVIEW_MARKER} mais"
    assert has_existing_opencode_review_comment(pr, [comment]) is True


def test_has_existing_comment_false():
    pr = MagicMock()
    assert has_existing_opencode_review_comment(pr, [MagicMock(body="nada")]) is False


def test_has_existing_comment_swallows_errors():
    pr = MagicMock()
    pr.get_issue_comments.side_effect = RuntimeError("boom")
    assert has_existing_opencode_review_comment(pr) is False
