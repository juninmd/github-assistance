"""Tests for structured review verdict parsing and the friendly PR comment."""

from dataclasses import replace

from src.agents.pr_assistant.review_verdict import (
    APPROVE,
    LABEL_APPROVED,
    LABEL_CHANGES,
    REQUEST_CHANGES,
    REVIEW_MARKER,
    build_review_comment,
    parse_review,
)


def test_parse_approve_json():
    verdict = parse_review('{"verdict":"APPROVE","summary":"Tudo certo"}', model="m")
    assert verdict is not None
    assert verdict.approved is True
    assert verdict.model == "m"
    assert verdict.label == LABEL_APPROVED


def test_parse_changes_with_findings_and_fence():
    text = (
        "Segue a analise:\n```json\n"
        '{"verdict":"REQUEST_CHANGES","summary":"Bug","findings":['
        '{"file":"a.py","line":"10","severity":"error","issue":"crash"}]}\n```'
    )
    verdict = parse_review(text)
    assert verdict is not None
    assert verdict.verdict == REQUEST_CHANGES
    assert verdict.findings[0].file == "a.py"
    assert verdict.findings[0].line == 10
    assert verdict.findings[0].severity == "error"
    assert verdict.label == LABEL_CHANGES


def test_parse_synonyms():
    lgtm = parse_review('{"verdict":"LGTM"}')
    rejected = parse_review('{"decision":"rejected"}')
    assert lgtm is not None and lgtm.verdict == APPROVE
    assert rejected is not None and rejected.verdict == REQUEST_CHANGES


def test_parse_invalid_returns_none():
    assert parse_review(None) is None
    assert parse_review("") is None
    assert parse_review("no json here") is None
    assert parse_review('{"verdict":"MAYBE"}') is None


def test_parse_findings_ignores_bad_entries():
    verdict = parse_review('{"verdict":"APPROVE","findings":["x",{"issue":"y"}]}')
    assert verdict is not None
    assert len(verdict.findings) == 1
    assert verdict.findings[0].line == 0


def test_build_comment_approved_has_emojis_marker_and_origin():
    verdict = parse_review('{"verdict":"APPROVE","summary":"Muito bom"}', model="litellm/cloud/auto")
    assert verdict is not None
    comment = build_review_comment(verdict, head_sha="abcdef123456")
    assert REVIEW_MARKER in comment
    assert "\u2705" in comment
    assert "Muito bom" in comment
    assert "abcdef12" in comment
    assert "github-assistance" in comment


def test_build_comment_changes_renders_table():
    verdict = parse_review(
        '{"verdict":"REQUEST_CHANGES","summary":"Corrigir","findings":['
        '{"file":"b.py","line":3,"severity":"warn","issue":"vaza segredo"}]}'
    )
    assert verdict is not None
    comment = build_review_comment(verdict)
    assert "\u274c" in comment
    assert "**Resumo:** Corrigir" in comment
    assert "### 🔎 Achados" in comment
    assert "### 🛠️ Correções" in comment
    assert "Nenhuma correção automática" in comment
    assert "b.py" in comment
    assert "vaza segredo" in comment
    assert "|---" in comment


def test_comment_reports_pushed_fixes():
    verdict = parse_review('{"verdict":"REQUEST_CHANGES","findings":[{"file":"a.py"}]}')
    assert verdict is not None
    fixed = replace(verdict, fixed=True, commit="deadbeef1234")
    comment = build_review_comment(fixed)
    assert "Correções aplicadas" in comment
    assert "deadbeef" in comment
    assert "Nenhuma correção automática" not in comment


def test_approved_comment_omits_fixes_section():
    verdict = parse_review('{"verdict":"APPROVE","summary":"ok"}')
    assert verdict is not None
    comment = build_review_comment(verdict)
    assert "### 🛠️ Correções" not in comment
    assert "Sem pontos bloqueantes" in comment

