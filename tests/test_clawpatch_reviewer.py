"""Tests for clawpatch_reviewer module."""
import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

from src.agents.pr_assistant.clawpatch_reviewer import (
    CLAWPATCH_MARKER,
    build_review_comment,
    has_existing_review_comment,
    review_pr_with_clawpatch,
)


def _make_pr(head_repo=True, head_ref="feature-branch", full_name="owner/repo"):
    pr = MagicMock()
    pr.head.ref = head_ref
    if head_repo:
        pr.head.repo = MagicMock()
        pr.head.repo.full_name = full_name
    else:
        pr.head.repo = None
    return pr


# ── has_existing_review_comment ──────────────────────────────────────────────


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
    # Passing list directly — get_issue_comments should NOT be called
    result = has_existing_review_comment(pr, issue_comments=[comment])
    pr.get_issue_comments.assert_not_called()
    assert result is True


def test_has_existing_review_comment_empty():
    pr = _make_pr()
    pr.get_issue_comments.return_value = []
    assert has_existing_review_comment(pr) is False


# ── build_review_comment ─────────────────────────────────────────────────────


def test_build_review_comment_with_report():
    comment = build_review_comment("## Findings\n- issue 1")
    assert CLAWPATCH_MARKER in comment
    assert "## Findings" in comment
    assert "clawpatch" in comment


def test_build_review_comment_empty_report():
    assert build_review_comment("") == ""


# ── review_pr_with_clawpatch ─────────────────────────────────────────────────


def test_review_pr_no_head_repo():
    pr = _make_pr(head_repo=False)
    success, msg = review_pr_with_clawpatch(pr)
    assert success is False
    assert "head repo" in msg.lower()


@patch("src.agents.pr_assistant.clawpatch_reviewer.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.clawpatch_reviewer._run")
@patch.dict("os.environ", {"GITHUB_TOKEN": "tok"})
def test_review_pr_success(mock_run, mock_tmpdir):
    mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/abc")
    mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

    report_result = MagicMock()
    report_result.stdout = "## Findings\n- bug found"

    # git clone, init, map, review, report
    mock_run.side_effect = [
        MagicMock(),   # git clone
        MagicMock(),   # clawpatch init
        MagicMock(),   # clawpatch map
        MagicMock(),   # clawpatch review
        report_result, # clawpatch report
    ]

    pr = _make_pr()
    success, report = review_pr_with_clawpatch(pr)
    assert success is True
    assert "bug found" in report


@patch("src.agents.pr_assistant.clawpatch_reviewer.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.clawpatch_reviewer._run")
@patch.dict("os.environ", {"GITHUB_TOKEN": "tok"})
def test_review_pr_clone_fails(mock_run, mock_tmpdir):
    mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/abc")
    mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

    mock_run.side_effect = subprocess.CalledProcessError(1, ["git", "clone"], "", "auth error")

    pr = _make_pr()
    success, msg = review_pr_with_clawpatch(pr)
    assert success is False
    assert "Clone failed" in msg


@patch("src.agents.pr_assistant.clawpatch_reviewer.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.clawpatch_reviewer._run")
@patch.dict("os.environ", {"GITHUB_TOKEN": "tok"})
def test_review_pr_clone_timeout(mock_run, mock_tmpdir):
    mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/abc")
    mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

    mock_run.side_effect = subprocess.TimeoutExpired(["git", "clone"], 120)

    pr = _make_pr()
    success, msg = review_pr_with_clawpatch(pr)
    assert success is False
    assert "timed out" in msg.lower()


@patch("src.agents.pr_assistant.clawpatch_reviewer.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.clawpatch_reviewer._run")
@patch.dict("os.environ", {"GITHUB_TOKEN": "tok"})
def test_review_pr_clawpatch_not_installed(mock_run, mock_tmpdir):
    mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/abc")
    mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

    mock_run.side_effect = [
        MagicMock(),        # git clone succeeds
        FileNotFoundError(),  # clawpatch init → not found
    ]

    pr = _make_pr()
    success, msg = review_pr_with_clawpatch(pr)
    assert success is False
    assert "not installed" in msg


@patch("src.agents.pr_assistant.clawpatch_reviewer.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.clawpatch_reviewer._run")
@patch.dict("os.environ", {"GITHUB_TOKEN": "tok"})
def test_review_pr_clawpatch_no_features(mock_run, mock_tmpdir):
    mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/abc")
    mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

    mock_run.side_effect = [
        MagicMock(),  # git clone
        MagicMock(),  # clawpatch init
        MagicMock(),  # clawpatch map
        subprocess.CalledProcessError(1, ["clawpatch", "review"], "", "No features to review"),
    ]

    pr = _make_pr()
    success, report = review_pr_with_clawpatch(pr)
    assert success is True
    assert report == ""


@patch("src.agents.pr_assistant.clawpatch_reviewer.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.clawpatch_reviewer._run")
@patch.dict("os.environ", {"GITHUB_TOKEN": "tok"})
def test_review_pr_review_timeout(mock_run, mock_tmpdir):
    mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/abc")
    mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

    mock_run.side_effect = [
        MagicMock(),  # git clone
        MagicMock(),  # clawpatch init
        MagicMock(),  # clawpatch map
        subprocess.TimeoutExpired(["clawpatch", "review"], 300),
    ]

    pr = _make_pr()
    success, msg = review_pr_with_clawpatch(pr)
    assert success is False
    assert "timed out" in msg.lower()


@patch("src.agents.pr_assistant.clawpatch_reviewer.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.clawpatch_reviewer._run")
@patch.dict("os.environ", {"GITHUB_TOKEN": "tok"})
def test_review_pr_report_fails(mock_run, mock_tmpdir):
    mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/abc")
    mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

    mock_run.side_effect = [
        MagicMock(),  # git clone
        MagicMock(),  # clawpatch init
        MagicMock(),  # clawpatch map
        MagicMock(),  # clawpatch review
        subprocess.CalledProcessError(1, ["clawpatch", "report"], "", "report error"),
    ]

    pr = _make_pr()
    success, msg = review_pr_with_clawpatch(pr)
    assert success is False
    assert "report" in msg.lower()


@patch("src.agents.pr_assistant.clawpatch_reviewer.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.clawpatch_reviewer._run")
@patch.dict("os.environ", {"GITHUB_TOKEN": "tok"})
def test_review_pr_empty_report(mock_run, mock_tmpdir):
    mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/abc")
    mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

    report_result = MagicMock()
    report_result.stdout = "   "  # whitespace only

    mock_run.side_effect = [
        MagicMock(),   # git clone
        MagicMock(),   # clawpatch init
        MagicMock(),   # clawpatch map
        MagicMock(),   # clawpatch review
        report_result, # clawpatch report
    ]

    pr = _make_pr()
    success, report = review_pr_with_clawpatch(pr)
    assert success is True
    assert report == ""
