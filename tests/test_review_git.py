"""Tests for committing/pushing review fixes to the PR branch."""

import src.agents.pr_assistant.review_git as rg


class _R:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


def _runner(results, calls=None):
    def _run(cmd, *a, **k):
        if calls is not None:
            calls.append(cmd)
        return results.pop(0)

    return _run


def test_commit_and_push_nothing_staged(monkeypatch):
    monkeypatch.setattr(rg, "proc_run", _runner([_R(0), _R(0), _R(0)]))
    assert rg.commit_and_push("/tmp", "feat", "msg") == (False, "")


def test_commit_and_push_stage_error(monkeypatch):
    monkeypatch.setattr(rg, "proc_run", _runner([_R(0), _R(0), _R(2)]))
    assert rg.commit_and_push("/tmp", "feat", "msg") == (False, "")


def test_commit_and_push_commit_fails(monkeypatch):
    monkeypatch.setattr(rg, "proc_run", _runner([_R(0), _R(0), _R(1), _R(1)]))
    assert rg.commit_and_push("/tmp", "feat", "msg") == (False, "")


def test_commit_and_push_push_fails(monkeypatch):
    monkeypatch.setattr(rg, "proc_run", _runner([_R(0), _R(0), _R(1), _R(0), _R(1)]))
    assert rg.commit_and_push("/tmp", "feat", "msg") == (False, "")


def test_commit_and_push_success(monkeypatch):
    results = [_R(0), _R(0), _R(1), _R(0), _R(0), _R(0, "abc123\n")]
    monkeypatch.setattr(rg, "proc_run", _runner(results))
    assert rg.commit_and_push("/tmp", "feat", "msg") == (True, "abc123")


def test_commit_and_push_never_commits_opencode_config(monkeypatch):
    calls: list = []
    results = [_R(0), _R(0), _R(0)]  # nothing staged afterwards
    monkeypatch.setattr(rg, "proc_run", _runner(results, calls))
    rg.commit_and_push("/tmp", "feat", "msg")
    assert ["git", "rm", "--cached", "--ignore-unmatch", "opencode.json"] in calls


def test_commit_and_push_timeout(monkeypatch):
    def _boom(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr(rg, "proc_run", _boom)
    assert rg.commit_and_push("/tmp", "feat", "msg") == (False, "")
