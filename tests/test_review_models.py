"""Tests for review model selection (free first, cloud/auto last)."""

import src.agents.pr_assistant.review_models as rm


class _Result:
    def __init__(self, out: str) -> None:
        self.stdout = out
        self.returncode = 0


def _reset():
    rm._cache = None


def test_free_models_filter_and_cache(monkeypatch):
    _reset()
    calls = {"n": 0}

    def _run(*a, **k):
        calls["n"] += 1
        return _Result("opencode/big-pickle\nopencode/x-free\nopencode/paid\n")

    monkeypatch.setattr(rm, "proc_run", _run)
    assert rm.free_opencode_models() == ["opencode/big-pickle", "opencode/x-free"]
    rm.free_opencode_models()
    assert calls["n"] == 1


def test_free_models_fallback_on_error(monkeypatch):
    _reset()

    def _boom(*a, **k):
        raise OSError("no opencode")

    monkeypatch.setattr(rm, "proc_run", _boom)
    assert rm.free_opencode_models() == ["opencode/big-pickle"]


def test_candidate_models_appends_cloud(monkeypatch):
    _reset()
    monkeypatch.setattr(rm, "free_opencode_models", lambda: ["opencode/x-free"])
    monkeypatch.setenv("OPENCODE_REVIEW_MODEL", "litellm/cloud/auto")
    assert rm.candidate_models() == ["opencode/x-free", "litellm/cloud/auto"]


def test_candidate_models_bounds_free(monkeypatch):
    _reset()
    monkeypatch.setattr(rm, "free_opencode_models", lambda: [f"m{i}-free" for i in range(10)])
    monkeypatch.setenv("OPENCODE_REVIEW_MAX_FREE_MODELS", "2")
    assert rm.candidate_models() == ["m0-free", "m1-free", "litellm/cloud/auto"]


def test_candidate_models_invalid_max_uses_default(monkeypatch):
    _reset()
    monkeypatch.setattr(rm, "free_opencode_models", lambda: ["a-free", "b-free", "c-free", "d-free"])
    monkeypatch.setenv("OPENCODE_REVIEW_MAX_FREE_MODELS", "abc")
    assert rm.candidate_models()[-1] == "litellm/cloud/auto"
    assert len(rm.candidate_models()) == 4
