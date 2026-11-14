"""Tests for LLM usage accounting and response cache."""

import pytest

from src.agents.core.metrics import AgentMetrics
from src.ai.base import AIClient
from src.ai.usage import estimate_tokens, usage


class FakeClient(AIClient):
    model = "fake"

    def __init__(self):
        self.n = 0

    def resolve_conflict(self, file_content, conflict_block):
        self.n += 1
        return "resolved"

    def generate_pr_comment(self, issue_description):
        return self.generate(issue_description)  # nested call

    def generate(self, prompt):
        self.n += 1
        if prompt == "boom":
            raise RuntimeError("x")
        return "answer " * 10


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("AI_CACHE", "1")
    usage.reset_counters()
    usage.clear_cache()
    yield


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcde") == 2


def test_cache_hit_skips_second_call_and_counts_savings():
    c = FakeClient()
    a, b = c.generate("p" * 400), c.generate("p" * 400)
    assert a == b and c.n == 1
    s = usage.snapshot()
    assert s["llm_calls"] == 1 and s["llm_cache_hits"] == 1
    assert s["llm_tokens_saved_est"] == 100 + estimate_tokens(a)
    assert s["llm_cache_hit_rate"] == 50.0


def test_nested_call_counted_once():
    FakeClient().generate_pr_comment("hello")
    assert usage.snapshot()["llm_calls"] == 1


def test_errors_counted_not_cached():
    c = FakeClient()
    for _ in range(2):
        with pytest.raises(RuntimeError):
            c.generate("boom")
    assert c.n == 2 and usage.snapshot()["llm_errors"] == 2


def test_resolve_conflict_never_cached():
    c = FakeClient()
    c.resolve_conflict("f", "b")
    c.resolve_conflict("f", "b")
    assert c.n == 2


def test_cache_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AI_CACHE", "0")
    c = FakeClient()
    c.generate("same")
    c.generate("same")
    assert c.n == 2


def test_sqlite_cache_persists_across_instances(tmp_path):
    usage.db_path = str(tmp_path / "c.db")
    try:
        FakeClient().generate("persist")
        usage.clear_cache()  # simulate new process
        c = FakeClient()
        c.generate("persist")
        assert c.n == 0
    finally:
        usage.db_path = None


def test_agent_metrics_reports_only_its_own_usage():
    FakeClient().generate("before")
    m = AgentMetrics("a")
    FakeClient().generate("during")
    out = m.finalize()
    assert out["llm_calls"] == 1 and out["llm_tokens_in_est"] == estimate_tokens("during")
