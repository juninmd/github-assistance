import pytest

from src.ai import usage as u


class _C:
    model = "m"

    def generate(self, prompt):
        return "ok"


def test_budget_blocks_calls_when_spent(monkeypatch):
    monkeypatch.setenv("AI_TOKEN_BUDGET", "10")
    monkeypatch.setattr(u, "usage", u.LLMUsage())
    f = u.instrument("generate", _C.generate)
    assert f(_C(), "hi") == "ok"
    with pytest.raises(u.TokenBudgetExceeded):
        f(_C(), "x" * 400)


def test_budget_default_unlimited(monkeypatch):
    monkeypatch.delenv("AI_TOKEN_BUDGET", raising=False)
    assert u.token_budget() == 0
    monkeypatch.setenv("AI_TOKEN_BUDGET", "bad")
    assert u.token_budget() == 0
