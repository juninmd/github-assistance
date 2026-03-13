from unittest.mock import MagicMock

from src.agents.pr_assistant.pipeline import (
    build_failure_comment,
    check_pipeline_status,
    has_existing_failure_comment,
)


def test_has_existing_failure_comment_true():
    pr = MagicMock()
    comment = MagicMock()
    comment.body = "Some text\n❌ **Pipeline Failure Detected**\nmore text"
    pr.get_issue_comments.return_value = [comment]
    assert has_existing_failure_comment(pr) is True


def test_has_existing_failure_comment_false():
    pr = MagicMock()
    comment = MagicMock()
    comment.body = "Looks good to me!"
    pr.get_issue_comments.return_value = [comment]
    assert has_existing_failure_comment(pr) is False


def test_has_existing_failure_comment_exception():
    pr = MagicMock()
    pr.get_issue_comments.side_effect = Exception("API Error")
    assert has_existing_failure_comment(pr) is False


def test_build_failure_comment():
    pr = MagicMock()
    pr.user.login = "testuser"
    failed_checks = [
        {"context": "lint", "description": "Linting failed", "url": "http://lint"},
        {"context": "test", "description": "Tests failed", "url": ""},
    ]
    comment = build_failure_comment(pr, failed_checks)

    assert "Hi @testuser" in comment
    assert "- **lint**: Linting failed ([details](http://lint))" in comment
    assert "- **test**: Tests failed" in comment


def test_check_pipeline_status_success_no_statuses():
    pr = MagicMock()
    repo = pr.base.repo
    commit = MagicMock()
    repo.get_commit.return_value = commit

    combined = MagicMock()
    combined.state = "pending"
    combined.total_count = 0
    commit.get_combined_status.return_value = combined

    commit.get_check_runs.return_value = []

    result = check_pipeline_status(pr)
    assert result["state"] == "success"
    assert len(result["failed_checks"]) == 0


def test_check_pipeline_status_failure_status():
    pr = MagicMock()
    repo = pr.base.repo
    commit = MagicMock()
    repo.get_commit.return_value = commit

    combined = MagicMock()
    combined.state = "failure"

    status = MagicMock()
    status.state = "failure"
    status.context = "CI"
    status.description = "CI failed"
    status.target_url = "http://ci"
    combined.statuses = [status]

    commit.get_combined_status.return_value = combined
    commit.get_check_runs.return_value = []

    result = check_pipeline_status(pr)
    assert result["state"] == "failure"
    assert len(result["failed_checks"]) == 1
    assert result["failed_checks"][0]["context"] == "CI"


def test_check_pipeline_status_check_run_failure():
    pr = MagicMock()
    repo = pr.base.repo
    commit = MagicMock()
    repo.get_commit.return_value = commit

    combined = MagicMock()
    combined.state = "success"
    commit.get_combined_status.return_value = combined

    check_run = MagicMock()
    check_run.conclusion = "failure"
    check_run.name = "Tests"
    check_run.output = {"summary": "Tests failed"}
    check_run.html_url = "http://tests"

    commit.get_check_runs.return_value = [check_run]

    result = check_pipeline_status(pr)
    assert result["state"] == "failure"
    assert len(result["failed_checks"]) == 1
    assert result["failed_checks"][0]["context"] == "Tests"


def test_check_pipeline_status_check_run_pending():
    pr = MagicMock()
    repo = pr.base.repo
    commit = MagicMock()
    repo.get_commit.return_value = commit

    combined = MagicMock()
    combined.state = "success"
    commit.get_combined_status.return_value = combined

    check_run = MagicMock()
    check_run.conclusion = None
    check_run.status = "in_progress"

    commit.get_check_runs.return_value = [check_run]

    result = check_pipeline_status(pr)
    assert result["state"] == "pending"
    assert len(result["failed_checks"]) == 0


def test_check_pipeline_status_exception():
    pr = MagicMock()
    pr.base.repo.get_commit.side_effect = Exception("API Error")

    result = check_pipeline_status(pr)
    assert result["state"] == "unknown"
    assert len(result["failed_checks"]) == 0
