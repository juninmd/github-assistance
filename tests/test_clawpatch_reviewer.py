"""Tests for local opencode PR review."""

from unittest.mock import MagicMock, patch

from src.agents.pr_assistant.clawpatch_reviewer import (
    CLAWPATCH_MARKER,
    build_review_comment,
    has_existing_review_comment,
    review_pr_with_clawpatch,
)


def _make_pr(files=None, head_ref="feature-branch", full_name="owner/repo"):
    pr = MagicMock()
    pr.number = 123
    pr.title = "Improve code"
    pr.html_url = "https://github.com/owner/repo/pull/123"
    pr.head.ref = head_ref
    pr.base.ref = "main"
    pr.base.repo.full_name = full_name
    if files is None:
        f = MagicMock()
        f.filename = "src/app.py"
        f.patch = "@@ -1 +1 @@\n-old\n+new"
        files = [f]
    pr.get_files.return_value = files
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


def test_build_review_comment_with_findings():
    comment = build_review_comment("STATUS: CHANGES\n- src/app.py: null deref")
    assert CLAWPATCH_MARKER in comment
    assert "opencode" in comment
    assert "null deref" in comment
    assert "Origem Automatizada" in comment


def test_build_review_comment_lgtm_is_empty():
    assert build_review_comment("STATUS: LGTM - no changes required") == ""


def test_build_review_comment_empty_report():
    assert build_review_comment("") == ""


def test_review_pr_no_diff():
    pr = _make_pr(files=[])
    success, msg = review_pr_with_clawpatch(pr)
    assert success is False
    assert "diff" in msg.lower()


@patch("src.agents.pr_assistant.clawpatch_reviewer.subprocess.run")
def test_review_pr_runs_opencode_locally(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="STATUS: CHANGES\n- bug here")

    pr = _make_pr()
    success, report = review_pr_with_clawpatch(pr)

    assert success is True
    assert "bug here" in report
    cmd = mock_run.call_args[0][0]
    assert "opencode" in cmd[0].lower()
    assert "run" in cmd
    assert any("Diff:" in str(a) for a in cmd)


@patch("src.agents.pr_assistant.clawpatch_reviewer.subprocess.run")
def test_review_pr_reports_opencode_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="")

    success, msg = review_pr_with_clawpatch(_make_pr())

    assert success is False
    assert "opencode review failed" in msg
