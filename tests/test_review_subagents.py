import threading
from unittest.mock import MagicMock, patch

from src.agents.pr_assistant import llm_reviewer
from src.agents.pr_assistant.review_subagents import (
    SPECIALISTS,
    active_specialists,
    merge_findings,
    review_with_subagents,
    subagents_enabled,
)


def _pr():
    pr = MagicMock()
    pr.title = "t"
    return pr


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LLM_REVIEW_SUBAGENTS", raising=False)
    assert subagents_enabled() is False


def test_merge_drops_empty_and_dedupes():
    out = merge_findings(
        {
            "Segurança": "- a.py: SQL injection in query",
            "Correção": "- a.py: sql injection in query!\n- b.py: off by one",
            "Testes": "No issues found.",
        }
    )
    assert out.count("injection") == 1 and "off by one" in out and "Testes" not in out


def test_all_clean_gives_empty_report():
    assert merge_findings({n: "No issues found." for n in SPECIALISTS}) == ""


def test_runs_specialists_in_parallel_with_distinct_focus():
    prompts, threads = [], set()
    client = MagicMock()

    def gen(prompt):
        prompts.append(prompt)
        threads.add(threading.get_ident())
        return "- x.py: bug"

    client.generate.side_effect = gen
    ok, report = review_with_subagents(_pr(), "diff", client)
    assert ok and len(prompts) == len(active_specialists()) and len(set(prompts)) == len(prompts)
    assert report.count("x.py: bug") == 1  # deduped across specialists


def test_one_failing_specialist_does_not_sink_review():
    client = MagicMock()
    client.generate.side_effect = [RuntimeError("boom"), "- y.py: leak", "No issues found."]
    ok, report = review_with_subagents(_pr(), "diff", client)
    assert ok and "y.py: leak" in report


def test_all_failing_reports_failure():
    client = MagicMock()
    client.generate.side_effect = RuntimeError("boom")
    ok, _ = review_with_subagents(_pr(), "diff", client)
    assert not ok


def test_reviewer_uses_subagents_only_for_big_diffs(monkeypatch):
    monkeypatch.setenv("LLM_REVIEW_SUBAGENTS", "true")
    monkeypatch.setenv("LLM_REVIEW_SUBAGENTS_MIN_CHARS", "50")
    client = MagicMock()
    client.generate.return_value = "No issues found."
    with patch.object(llm_reviewer, "collect_diff", return_value="x" * 10):
        llm_reviewer.review_pr_with_litellm(_pr(), client)
    assert client.generate.call_count == 1  # small diff: single generalist call
    client.generate.reset_mock()
    with patch.object(llm_reviewer, "collect_diff", return_value="x" * 100):
        assert llm_reviewer.review_pr_with_litellm(_pr(), client) == (True, "")
    assert client.generate.call_count == len(active_specialists())
