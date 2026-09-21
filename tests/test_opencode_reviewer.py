from unittest.mock import MagicMock, patch

from src.agents.pr_assistant.opencode_reviewer import (
    build_opencode_review_comment,
    has_existing_opencode_review_comment,
    opencode_review_enabled,
    review_pr_with_opencode,
)


def test_opencode_review_enabled_defaults_off(monkeypatch):
    monkeypatch.delenv("OPENCODE_REVIEW_ENABLED", raising=False)
    assert opencode_review_enabled() is False


def test_opencode_review_enabled_true(monkeypatch):
    monkeypatch.setenv("OPENCODE_REVIEW_ENABLED", "1")
    assert opencode_review_enabled() is True


def test_has_existing_opencode_review_comment_true():
    pr = MagicMock()
    comment = MagicMock()
    comment.body = "<!-- opencode-review -->\nsome text"
    pr.get_issue_comments.return_value = [comment]
    assert has_existing_opencode_review_comment(pr) is True


def _pr_with_patch(patch_text: str):
    pr = MagicMock()
    pr.title = "Fix bug"
    f = MagicMock()
    f.filename = "app.py"
    f.patch = patch_text
    pr.get_files.return_value = [f]
    return pr


def test_review_pr_with_opencode_no_diff_skips_subprocess():
    pr = MagicMock()
    pr.get_files.return_value = []

    with patch("src.agents.pr_assistant.opencode_reviewer.proc_run") as mock_run:
        success, report = review_pr_with_opencode(pr)

    assert success is True
    assert report == ""
    mock_run.assert_not_called()


@patch("src.agents.pr_assistant.opencode_reviewer._get_free_opencode_models", return_value=["opencode/free-a"])
@patch("src.agents.pr_assistant.opencode_reviewer.proc_run")
def test_review_pr_with_opencode_reports_findings(mock_run, _mock_models):
    pr = _pr_with_patch("+eval(user_input)")
    mock_run.return_value = MagicMock(returncode=0, stdout="- app.py: uses eval() on user input")

    success, report = review_pr_with_opencode(pr)

    assert success is True
    assert "eval" in report
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["cwd"]  # ran in a scratch temp dir


@patch("src.agents.pr_assistant.opencode_reviewer._get_free_opencode_models", return_value=["opencode/free-a"])
@patch("src.agents.pr_assistant.opencode_reviewer.proc_run")
def test_review_pr_with_opencode_no_issues_returns_empty_report(mock_run, _mock_models):
    pr = _pr_with_patch("+x = 1")
    mock_run.return_value = MagicMock(returncode=0, stdout="No issues found.")

    success, report = review_pr_with_opencode(pr)

    assert success is True
    assert report == ""


@patch(
    "src.agents.pr_assistant.opencode_reviewer._get_free_opencode_models",
    return_value=["opencode/free-a", "opencode/free-b"],
)
@patch("src.agents.pr_assistant.opencode_reviewer.proc_run")
def test_review_pr_with_opencode_falls_back_across_free_models(mock_run, _mock_models):
    pr = _pr_with_patch("+x = 1")
    mock_run.side_effect = [
        MagicMock(returncode=1, stdout=""),
        MagicMock(returncode=0, stdout="- app.py: issue via second model"),
    ]

    success, report = review_pr_with_opencode(pr)

    assert success is True
    assert "second model" in report
    assert mock_run.call_count == 2


@patch("src.agents.pr_assistant.opencode_reviewer._get_free_opencode_models", return_value=["opencode/free-a"])
@patch("src.agents.pr_assistant.opencode_reviewer.proc_run")
def test_review_pr_with_opencode_all_models_fail_is_non_fatal(mock_run, _mock_models):
    pr = _pr_with_patch("+x = 1")
    mock_run.return_value = MagicMock(returncode=1, stdout="")

    success, report = review_pr_with_opencode(pr)

    assert success is False
    assert "opencode/free-a" in report


def test_build_opencode_review_comment_empty_report_yields_empty_comment():
    assert build_opencode_review_comment("") == ""


def test_build_opencode_review_comment_includes_marker_and_disclaimer():
    comment = build_opencode_review_comment("- issue found")
    assert "<!-- opencode-review -->" in comment
    assert "modelos gratuitos" in comment
    assert "não afeta a decisão de merge" in comment
