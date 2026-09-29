"""Tests for committing/pushing review fixes to the PR branch."""

from unittest.mock import MagicMock

import src.agents.pr_assistant.review_git as rg


class _R:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


def test_commit_and_push_nothing_staged(monkeypatch):
    monkeypatch.setattr(rg, "proc_run", lambda *a, **k: _R(0))
    assert rg.commit_and_push("/tmp", "feat", "msg") == (False, "")


def test_commit_and_push_stage_error(monkeypatch):
    monkeypatch.setattr(rg, "proc_run", lambda *a, **k: _R(2))
    assert rg.commit_and_push("/tmp", "feat", "msg") == (False, "")


def test_commit_and_push_commit_fails(monkeypatch):
    results = [_R(0), _R(1), _R(1)]
    monkeypatch.setattr(rg, "proc_run", lambda *a, **k: results.pop(0))
    assert rg.commit_and_push("/tmp", "feat", "msg") == (False, "")


def test_commit_and_push_push_fails(monkeypatch):
    results = [_R(0), _R(1), _R(0), _R(1)]
    monkeypatch.setattr(rg, "proc_run", lambda *a, **k: results.pop(0))
    assert rg.commit_and_push("/tmp", "feat", "msg") == (False, "")


def test_commit_and_push_success(monkeypatch):
    results = [_R(0), _R(1), _R(0), _R(0), _R(0, "abc123\n")]
    monkeypatch.setattr(rg, "proc_run", lambda *a, **k: results.pop(0))
    assert rg.commit_and_push("/tmp", "feat", "msg") == (True, "abc123")


def test_commit_and_push_timeout(monkeypatch):
    monkeypatch.setattr(rg, "proc_run", MagicMock(side_effect=OSError("boom")))
    assert rg.commit_and_push("/tmp", "feat", "msg") == (False, "")
