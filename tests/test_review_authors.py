"""Tests for PR author classification (Jules vs owner)."""

from src.agents.pr_assistant.review_authors import is_jules, is_owner, should_autofix


def test_is_jules_variants():
    assert is_jules("google-labs-jules")
    assert is_jules("google-labs-jules[bot]")
    assert is_jules("Jules da Google")
    assert not is_jules("juninmd")
    assert not is_jules(None)


def test_is_owner(monkeypatch):
    monkeypatch.setenv("GITHUB_OWNER", "juninmd")
    assert is_owner("juninmd")
    assert is_owner("JUNINMD")
    assert not is_owner("someone")


def test_should_autofix_only_owner(monkeypatch):
    monkeypatch.setenv("GITHUB_OWNER", "juninmd")
    assert should_autofix("juninmd")
    assert not should_autofix("google-labs-jules[bot]")
    assert not should_autofix("dependabot[bot]")
