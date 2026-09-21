from unittest.mock import MagicMock

from src.agents.pr_assistant.llm_reviewer import (
    build_llm_review_comment,
    has_existing_llm_review_comment,
    llm_review_enabled,
    review_pr_with_litellm,
)


def test_llm_review_enabled_defaults_off(monkeypatch):
    monkeypatch.delenv("LLM_REVIEW_ENABLED", raising=False)
    assert llm_review_enabled() is False


def test_llm_review_enabled_true(monkeypatch):
    monkeypatch.setenv("LLM_REVIEW_ENABLED", "true")
    assert llm_review_enabled() is True


def test_has_existing_llm_review_comment_true():
    pr = MagicMock()
    comment = MagicMock()
    comment.body = "<!-- litellm-review -->\nsome text"
    pr.get_issue_comments.return_value = [comment]
    assert has_existing_llm_review_comment(pr) is True


def test_has_existing_llm_review_comment_false():
    pr = MagicMock()
    comment = MagicMock()
    comment.body = "unrelated"
    pr.get_issue_comments.return_value = [comment]
    assert has_existing_llm_review_comment(pr) is False


def _pr_with_patch(patch_text: str):
    pr = MagicMock()
    pr.title = "Fix bug"
    f = MagicMock()
    f.filename = "app.py"
    f.patch = patch_text
    pr.get_files.return_value = [f]
    return pr


def test_review_pr_with_litellm_reports_findings():
    pr = _pr_with_patch("+eval(user_input)")
    ai_client = MagicMock()
    ai_client.generate.return_value = "- app.py: uses eval() on user input"

    success, report = review_pr_with_litellm(pr, ai_client)

    assert success is True
    assert "eval" in report
    ai_client.generate.assert_called_once()


def test_review_pr_with_litellm_no_issues_returns_empty_report():
    pr = _pr_with_patch("+x = 1")
    ai_client = MagicMock()
    ai_client.generate.return_value = "No issues found."

    success, report = review_pr_with_litellm(pr, ai_client)

    assert success is True
    assert report == ""


def test_review_pr_with_litellm_no_diff_skips_model_call():
    pr = MagicMock()
    pr.get_files.return_value = []
    ai_client = MagicMock()

    success, report = review_pr_with_litellm(pr, ai_client)

    assert success is True
    assert report == ""
    ai_client.generate.assert_not_called()


def test_review_pr_with_litellm_model_error_is_non_fatal():
    pr = _pr_with_patch("+x = 1")
    ai_client = MagicMock()
    ai_client.generate.side_effect = Exception("proxy unreachable")

    success, report = review_pr_with_litellm(pr, ai_client)

    assert success is False
    assert "proxy unreachable" in report


def test_build_llm_review_comment_empty_report_yields_empty_comment():
    assert build_llm_review_comment("") == ""


def test_build_llm_review_comment_includes_marker_and_disclaimer():
    comment = build_llm_review_comment("- issue found")
    assert "<!-- litellm-review -->" in comment
    assert "não afeta a decisão de merge" in comment
