from types import SimpleNamespace

from src.agents.pr_assistant import pr_evidence, review_flow
from src.agents.pr_assistant import review_verdict as rv


def test_image_counts_as_evidence():
    assert pr_evidence.has_evidence("Antes ![a](https://x/y.png)")


def test_empty_section_is_not_evidence():
    assert not pr_evidence.has_evidence("### Evidências\n<!-- anexe -->\n\n### Outro\nx")


def test_section_with_content_is_evidence():
    assert pr_evidence.has_evidence("### Evidências\n```\n12 passed in 1.2s, 0 failed\n```")


def test_missing_evidence_warns_without_blocking(monkeypatch):
    monkeypatch.delenv("REVIEW_REQUIRE_EVIDENCE", raising=False)
    base = rv.ReviewVerdict(verdict=rv.APPROVE, summary="ok")
    out = review_flow._with_evidence(SimpleNamespace(body="sem nada"), base)
    assert out.approved and out.findings[0].severity == "warn"
    assert not out.blocks("error")


def test_flag_disables_check(monkeypatch):
    monkeypatch.setenv("REVIEW_REQUIRE_EVIDENCE", "false")
    base = rv.ReviewVerdict(verdict=rv.APPROVE, summary="ok")
    assert review_flow._with_evidence(SimpleNamespace(body=""), base) == base
