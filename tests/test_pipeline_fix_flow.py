"""Tests for the pr_assistant pipeline-fix flow."""

from unittest.mock import MagicMock

from src.agents.pr_assistant import pipeline_fix_flow


def _pr():
    pr = MagicMock()
    pr.number = 9
    pr.head.sha = "sha1"
    pr.user.login = "juninmd"
    return pr


def test_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(pipeline_fix_flow, "pipeline_fix_enabled", lambda: False)
    assert pipeline_fix_flow.attempt_pipeline_fix(_pr(), MagicMock(), MagicMock()) is False


def test_not_failing_is_noop(monkeypatch):
    monkeypatch.setattr(pipeline_fix_flow, "pipeline_fix_enabled", lambda: True)
    monkeypatch.setattr(pipeline_fix_flow, "check_pipeline_status", lambda pr: {"state": "success"})
    assert pipeline_fix_flow.attempt_pipeline_fix(_pr(), MagicMock(), MagicMock()) is False


def test_exhausted_marks_manual(monkeypatch):
    gc = MagicMock()
    monkeypatch.setattr(pipeline_fix_flow, "pipeline_fix_enabled", lambda: True)
    monkeypatch.setattr(pipeline_fix_flow, "check_pipeline_status", lambda pr: {"state": "failure"})
    monkeypatch.setattr(pipeline_fix_flow, "read_attempt_state", lambda c: (3, ""))
    monkeypatch.setattr(pipeline_fix_flow, "max_attempts", lambda: 3)
    assert pipeline_fix_flow.attempt_pipeline_fix(_pr(), gc, MagicMock()) is False
    gc.add_label_to_pr.assert_called_once()


def test_no_logs_is_noop(monkeypatch):
    gc = MagicMock()
    monkeypatch.setattr(pipeline_fix_flow, "pipeline_fix_enabled", lambda: True)
    monkeypatch.setattr(pipeline_fix_flow, "check_pipeline_status", lambda pr: {"state": "failure"})
    monkeypatch.setattr(pipeline_fix_flow, "read_attempt_state", lambda c: (0, ""))
    monkeypatch.setattr(pipeline_fix_flow, "max_attempts", lambda: 3)
    monkeypatch.setattr(pipeline_fix_flow, "get_pipeline_error_logs", lambda pr: {"logs": ""})
    assert pipeline_fix_flow.attempt_pipeline_fix(_pr(), gc, MagicMock()) is False
    gc.comment_on_pr.assert_not_called()


def test_success_pushes_and_comments(monkeypatch):
    gc = MagicMock()
    monkeypatch.setattr(pipeline_fix_flow, "pipeline_fix_enabled", lambda: True)
    monkeypatch.setattr(pipeline_fix_flow, "check_pipeline_status", lambda pr: {"state": "failure"})
    monkeypatch.setattr(pipeline_fix_flow, "read_attempt_state", lambda c: (0, ""))
    monkeypatch.setattr(pipeline_fix_flow, "max_attempts", lambda: 3)
    monkeypatch.setattr(
        pipeline_fix_flow, "get_pipeline_error_logs",
        lambda pr: {"logs": "boom", "failed_checks": ["validate"]},
    )
    monkeypatch.setattr(
        pipeline_fix_flow, "fix_pipeline_autonomously",
        lambda pr, logs, checks, attempt, mx: (True, "fixed", "newsha"),
    )
    assert pipeline_fix_flow.attempt_pipeline_fix(_pr(), gc, MagicMock()) is True
    gc.comment_on_pr.assert_called_once()


def test_failure_after_max_marks_manual(monkeypatch):
    gc = MagicMock()
    monkeypatch.setattr(pipeline_fix_flow, "pipeline_fix_enabled", lambda: True)
    monkeypatch.setattr(pipeline_fix_flow, "check_pipeline_status", lambda pr: {"state": "failure"})
    monkeypatch.setattr(pipeline_fix_flow, "read_attempt_state", lambda c: (2, ""))
    monkeypatch.setattr(pipeline_fix_flow, "max_attempts", lambda: 3)
    monkeypatch.setattr(
        pipeline_fix_flow, "get_pipeline_error_logs",
        lambda pr: {"logs": "boom", "failed_checks": ["validate"]},
    )
    monkeypatch.setattr(
        pipeline_fix_flow, "fix_pipeline_autonomously",
        lambda pr, logs, checks, attempt, mx: (False, "nope", ""),
    )
    assert pipeline_fix_flow.attempt_pipeline_fix(_pr(), gc, MagicMock()) is False
    gc.add_label_to_pr.assert_called_once()


def test_exception_swallowed(monkeypatch):
    monkeypatch.setattr(pipeline_fix_flow, "pipeline_fix_enabled", lambda: True)
    monkeypatch.setattr(
        pipeline_fix_flow, "check_pipeline_status",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    assert pipeline_fix_flow.attempt_pipeline_fix(_pr(), MagicMock(), MagicMock()) is False
