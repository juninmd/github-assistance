from unittest.mock import MagicMock

from src.agents.pr_assistant import review_advisories as adv
from src.agents.pr_assistant.pr_diff import build_review_prompt
from src.agents.pr_assistant.review_flow import _instructions
from src.agents.pr_assistant.review_subagents import (
    active_specialists,
    review_with_subagents,
    specialist_prompt,
)


def _pr(readme="# Proj\nuse npm start"):
    pr = MagicMock()
    pr.title = "chore: deps"
    pr.base.repo.get_readme.return_value.decoded_content = readme.encode()
    return pr


def test_rules_mention_stack_and_readme():
    assert "Node.js→Bun" in adv.RULES and "JavaScript→TypeScript" in adv.RULES
    assert "README" in adv.RULES and "não bloqueante" in adv.RULES


def test_generalist_prompt_includes_rules_and_readme():
    p = build_review_prompt(_pr(), "diff")
    assert "Node.js→Bun" in p and "npm start" in p


def test_disabled_flag_removes_everything(monkeypatch):
    monkeypatch.setenv("REVIEW_ADVISORIES", "false")
    p = build_review_prompt(_pr(), "diff")
    assert "Bun" not in p and "README" not in p
    assert "Stack e docs" not in active_specialists()
    assert "Bun" not in _instructions(_pr())


def test_opencode_instructions_include_rules():
    assert "Node.js→Bun" in _instructions(_pr())


def test_specialist_added_and_gets_readme():
    team = active_specialists()
    assert "Stack e docs" in team and len(team) == 4
    assert "npm start" in specialist_prompt(_pr(), "d", team["Stack e docs"])
    assert "npm start" not in specialist_prompt(_pr(), "d", team["Segurança"])


def test_readme_failure_and_truncation():
    pr = _pr("x" * 5000)
    assert len(adv.readme_excerpt(pr)) == 1500
    pr.base.repo.get_readme.side_effect = RuntimeError
    assert adv.readme_excerpt(pr) == ""


def test_subagents_run_four():
    ai = MagicMock()
    ai.generate.return_value = "- a.py: x"
    ok, _ = review_with_subagents(_pr(), "d", ai)
    assert ok and ai.generate.call_count == 4
