"""Tests for PR review delegation."""

from unittest.mock import MagicMock, patch

from src.agents.pr_assistant.clawpatch_reviewer import (
    CLAWPATCH_MARKER,
    build_review_comment,
    has_existing_review_comment,
    review_pr_with_clawpatch,
)


def _make_pr(head_repo=True, head_ref="feature-branch", full_name="owner/repo"):
    pr = MagicMock()
    pr.number = 123
    pr.title = "Improve code"
    pr.html_url = "https://github.com/owner/repo/pull/123"
    pr.head.ref = head_ref
    pr.base.ref = "main"
    pr.base.repo.full_name = full_name
    if head_repo:
        pr.head.repo = MagicMock()
        pr.head.repo.full_name = full_name
    else:
        pr.head.repo = None
    return pr


def test_has_existing_review_comment_true():
    pr = _make_pr()
    comment = MagicMock()
    comment.body = f"some text {CLAWPATCH_MARKER} more"
    pr.get_issue_comments.return_value = [comment]
    assert has_existing_review_comment(pr) is True


def test_has_existing_review_comment_false():
    pr = _make_pr()
    comment = MagicMock()
    comment.body = "regular comment"
    pr.get_issue_comments.return_value = [comment]
    assert has_existing_review_comment(pr) is False


def test_has_existing_review_comment_uses_provided_list():
    pr = _make_pr()
    comment = MagicMock()
    comment.body = CLAWPATCH_MARKER
    result = has_existing_review_comment(pr, issue_comments=[comment])
    pr.get_issue_comments.assert_not_called()
    assert result is True


def test_build_review_comment_with_report():
    comment = build_review_comment("Review delegated to Vibe-Code task: http://localhost/tasks/1")
    assert CLAWPATCH_MARKER in comment
    assert "vibe-code/opencode" in comment
    assert "Origem Automatizada" in comment


def test_build_review_comment_empty_report():
    assert build_review_comment("") == ""


def test_review_pr_no_head_repo():
    pr = _make_pr(head_repo=False)
    success, msg = review_pr_with_clawpatch(pr)
    assert success is False
    assert "head repo" in msg.lower()


@patch("src.agents.pr_assistant.clawpatch_reviewer.VibeCodeClient")
def test_review_pr_creates_vibe_code_opencode_task(mock_client_cls):
    client = mock_client_cls.return_value
    client.create_opencode_task.return_value = {"task_url": "http://localhost:3000/tasks/t1"}

    pr = _make_pr()
    success, report = review_pr_with_clawpatch(pr)

    assert success is True
    assert "Vibe-Code task" in report
    client.create_opencode_task.assert_called_once()
    _args, kwargs = client.create_opencode_task.call_args
    assert kwargs["repository"] == "owner/repo"
    assert kwargs["base_branch"] == "main"
    assert "PR URL: https://github.com/owner/repo/pull/123" in kwargs["instructions"]


@patch("src.agents.pr_assistant.clawpatch_reviewer.VibeCodeClient")
def test_review_pr_reports_vibe_code_failure(mock_client_cls):
    mock_client_cls.return_value.create_opencode_task.side_effect = RuntimeError("offline")

    success, msg = review_pr_with_clawpatch(_make_pr())

    assert success is False
    assert "vibe-code task creation failed" in msg
