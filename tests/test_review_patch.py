"""Tests for the deterministic patch-based auto-fix."""

from unittest.mock import MagicMock

from src.agents.pr_assistant import review_patch
from src.agents.pr_assistant.review_verdict import REQUEST_CHANGES, Finding, ReviewVerdict


def _verdict() -> ReviewVerdict:
    return ReviewVerdict(
        verdict=REQUEST_CHANGES, summary="x", findings=[Finding("a.py", 3, "error", "bug")], model="m"
    )


def test_fix_prompt_lists_findings():
    prompt = review_patch.fix_prompt(_verdict())
    assert "a.py" in prompt and "bug" in prompt and "diff --git" in prompt


def test_extract_patch_from_fence():
    text = "claro:\n```diff\ndiff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-1\n+2\n```\nfim"
    patch = review_patch.extract_patch(text)
    assert patch.startswith("diff --git")
    assert "-1" in patch and "+2" in patch


def test_extract_patch_from_plain_diff():
    text = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-1\n+2"
    assert review_patch.extract_patch(text).startswith("diff --git")


def test_extract_patch_none():
    assert review_patch.extract_patch(None) == ""
    assert review_patch.extract_patch("no patch here") == ""


def test_request_patch_returns_extracted(monkeypatch):
    monkeypatch.setattr(review_patch.ws, "run_opencode", lambda *a, **k: "```\ndiff --git a/x b/x\n```")
    assert review_patch.request_patch("/tmp", _verdict(), "m").startswith("diff --git")


def test_request_patch_none_when_opencode_fails(monkeypatch):
    monkeypatch.setattr(review_patch.ws, "run_opencode", lambda *a, **k: None)
    assert review_patch.request_patch("/tmp", _verdict(), "m") == ""


def test_apply_patch_delegates(monkeypatch):
    called = {}

    def _fake(d, p):
        called["args"] = (d, p)
        return True

    monkeypatch.setattr(review_patch.review_git, "apply_patch", _fake)
    assert review_patch.apply_patch("/tmp", "diff") is True
    assert called["args"] == ("/tmp", "diff")


def test_git_apply_patch(monkeypatch):
    from src.agents.pr_assistant import review_git

    monkeypatch.setattr(review_git, "proc_run", lambda *a, **k: MagicMock(returncode=0))
    assert review_git.apply_patch("/tmp", "diff --git a/a b/a") is True
    assert review_git.apply_patch("/tmp", "") is False
    monkeypatch.setattr(review_git, "proc_run", lambda *a, **k: MagicMock(returncode=1))
    assert review_git.apply_patch("/tmp", "diff") is False
