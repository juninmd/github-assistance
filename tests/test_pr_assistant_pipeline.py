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


from unittest.mock import patch


def test_extract_coverage():
    from src.agents.pr_assistant.pipeline import _extract_coverage

    assert _extract_coverage(None) is None
    assert _extract_coverage("No coverage info") is None
    assert _extract_coverage("Coverage is 85.5%") == 85.5

    # We need to cover the ValueError branch for float conversion.
    with patch("src.agents.pr_assistant.pipeline._COVERAGE_RE") as mock_re:
        mock_match = MagicMock()
        mock_match.group.return_value = "invalid"
        mock_re.search.return_value = mock_match

        assert _extract_coverage("Coverage is invalid%") is None


def test_check_pipeline_status_coverage_from_statuses():
    pr = MagicMock()
    repo = pr.base.repo
    commit = MagicMock()
    repo.get_commit.return_value = commit

    combined = MagicMock()
    combined.state = "success"
    status1 = MagicMock()
    status1.description = "Coverage is 90.5%"
    status1.context = "codecov"
    combined.statuses = [status1]
    commit.get_combined_status.return_value = combined
    commit.get_check_runs.return_value = []

    from src.agents.pr_assistant.pipeline import check_pipeline_status
    result = check_pipeline_status(pr)
    assert len(result["coverage"]) == 1
    assert result["coverage"][0]["coverage"] == 90.5


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


def test_check_pipeline_status_extracts_coverage_from_summary():
    pr = MagicMock()
    repo = pr.base.repo
    commit = MagicMock()
    repo.get_commit.return_value = commit

    combined = MagicMock()
    combined.state = "success"
    commit.get_combined_status.return_value = combined

    check_run = MagicMock()
    check_run.conclusion = "success"
    check_run.name = "Coverage"
    check_run.status = "completed"
    check_run.output = {"summary": "Coverage: 84.5%"}
    check_run.html_url = "http://coverage"

    commit.get_check_runs.return_value = [check_run]

    result = check_pipeline_status(pr)
    assert result["state"] == "success"
    assert "coverage" in result
    assert result["coverage"][0]["coverage"] == 84.5


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
