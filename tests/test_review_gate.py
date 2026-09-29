"""Tests for the critical review gate (draft + commit status)."""

from unittest.mock import MagicMock

from src.agents.pr_assistant import review_gate
from src.agents.pr_assistant.review_verdict import (
    APPROVE,
    GATE_NAME,
    LABEL_CRITICAL,
    REQUEST_CHANGES,
    Finding,
    ReviewVerdict,
)


def _pr(draft: bool = False):
    pr = MagicMock()
    pr.number = 7
    pr.head.sha = "sha123"
    pr.draft = draft
    pr.base.repo.get_labels.return_value = []
    return pr


def _verdict(severity: str, verdict: str) -> ReviewVerdict:
    return ReviewVerdict(
        verdict=verdict, summary="x", findings=[Finding("a.py", 1, severity, "issue")], model="m"
    )


def test_gate_disabled_is_noop():
    pr = _pr()
    review_gate.apply_gate(pr, MagicMock(), _verdict("error", REQUEST_CHANGES), False, MagicMock())
    pr.base.repo.get_commit.assert_not_called()
    pr.convert_to_draft.assert_not_called()


def test_gate_critical_drafts_and_publishes_failure():
    pr = _pr(draft=False)
    gc = MagicMock()
    review_gate.apply_gate(pr, gc, _verdict("error", REQUEST_CHANGES), True, MagicMock())
    pr.convert_to_draft.assert_called_once()
    gc.add_label_to_pr.assert_called_once_with(pr, LABEL_CRITICAL)
    status = pr.base.repo.get_commit.return_value.create_status
    assert status.call_args.kwargs["state"] == "failure"
    assert status.call_args.kwargs["context"] == GATE_NAME


def test_gate_approve_publishes_success_and_readies():
    pr = _pr(draft=True)
    gc = MagicMock()
    review_gate.apply_gate(pr, gc, _verdict("warn", APPROVE), True, MagicMock())
    status = pr.base.repo.get_commit.return_value.create_status
    assert status.call_args.kwargs["state"] == "success"
    pr.mark_ready_for_review.assert_called_once()
    pr.as_issue.return_value.remove_from_labels.assert_called_once_with(LABEL_CRITICAL)


def test_gate_drafts_even_when_status_fails():
    pr = _pr(draft=False)
    pr.base.repo.get_commit.return_value.create_status.side_effect = RuntimeError("app only")
    log = MagicMock()
    review_gate.apply_gate(pr, MagicMock(), _verdict("error", REQUEST_CHANGES), True, log)
    pr.convert_to_draft.assert_called_once()
    log.assert_called()


def test_gate_enabled_env(monkeypatch):
    monkeypatch.delenv("REVIEW_GATE_ENABLED", raising=False)
    assert review_gate.gate_enabled() is True
    monkeypatch.setenv("REVIEW_GATE_ENABLED", "false")
    assert review_gate.gate_enabled() is False
