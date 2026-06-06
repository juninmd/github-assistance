from unittest.mock import MagicMock, patch

from src.agents.pr_assistant.pipeline import (
    build_failure_comment,
    check_pipeline_status,
    get_pipeline_error_logs,
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


def test_check_pipeline_status_ignorable_check_run_failure_still_blocks():
    pr = MagicMock()
    repo = pr.base.repo
    commit = MagicMock()
    repo.get_commit.return_value = commit

    combined = MagicMock()
    combined.state = "success"
    combined.statuses = []
    commit.get_combined_status.return_value = combined

    check_run = MagicMock()
    check_run.conclusion = "failure"
    check_run.name = "Snyk Security"
    check_run.output = {"summary": "Vulnerabilities found"}
    check_run.html_url = "http://snyk"

    commit.get_check_runs.return_value = [check_run]

    result = check_pipeline_status(pr)
    assert result["state"] == "failure"
    assert result["failed_checks"][0]["context"] == "Snyk Security"


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
    combined.statuses = []
    commit.get_combined_status.return_value = combined

    check_run = MagicMock()
    check_run.name = "ci"
    check_run.conclusion = None
    check_run.status = "in_progress"
    check_run.output = None

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


def _job(name, conclusion, job_id):
    j = MagicMock()
    j.name = name
    j.conclusion = conclusion
    j.id = job_id
    return j


@patch("src.agents.pr_assistant.pipeline.requests.get")
def test_get_pipeline_error_logs_from_jobs(mock_get):
    pr = MagicMock()
    pr.head.sha = "abc"
    repo = pr.base.repo
    repo.full_name = "owner/repo"

    run = MagicMock()
    run.conclusion = "failure"
    run.jobs.return_value = [
        _job("build", "failure", 11),
        _job("sonar", "failure", 12),  # ignorable
        _job("ok", "success", 13),
    ]
    repo.get_workflow_runs.return_value = [run]

    resp = MagicMock()
    resp.status_code = 200
    resp.text = "2024-01-01T00:00:00.0Z line1\n2024-01-01T00:00:01.0Z error: boom\n"
    mock_get.return_value = resp

    result = get_pipeline_error_logs(pr, token="tkn")

    assert "build" in result["failed_checks"]
    assert "sonar" not in result["failed_checks"]
    assert "error: boom" in result["logs"]
    # timestamp stripped
    assert "2024-01-01T00:00:01" not in result["logs"]


@patch("src.agents.pr_assistant.pipeline.requests.get")
def test_get_pipeline_error_logs_filters_journal_noise(mock_get):
    pr = MagicMock()
    pr.head.sha = "abc"
    repo = pr.base.repo
    repo.full_name = "owner/repo"
    run = MagicMock()
    run.conclusion = "failure"
    run.jobs.return_value = [_job("build", "failure", 11)]
    repo.get_workflow_runs.return_value = [run]

    noisy = "\n".join(
        [
            "running cargo test",
            "error[E0277]: the trait bound is not satisfied",
            "##[error]Process completed with exit code 1.",
        ]
        # harden-runner / journal noise dumped during post-job cleanup
        + [f"Jun 04 15:31:5{i} runnervm agentservice[2254]: module=armour noise" for i in range(9)]
    )
    resp = MagicMock()
    resp.status_code = 200
    resp.text = noisy
    mock_get.return_value = resp

    result = get_pipeline_error_logs(pr, token="tkn")

    assert "error[E0277]" in result["logs"]
    assert "##[error]Process completed" in result["logs"]
    assert "module=armour" not in result["logs"]


@patch("src.agents.pr_assistant.pipeline.requests.get")
def test_get_pipeline_error_logs_falls_back_to_check_runs(mock_get):
    pr = MagicMock()
    pr.head.sha = "abc"
    repo = pr.base.repo
    repo.full_name = "owner/repo"
    repo.get_workflow_runs.return_value = []  # no runs -> fallback

    commit = MagicMock()
    repo.get_commit.return_value = commit
    check = MagicMock()
    check.conclusion = "failure"
    check.name = "pytest"
    check.output = {"summary": "assert failed in test_x"}
    ann = MagicMock()
    ann.path = "app.py"
    ann.start_line = 10
    ann.message = "NameError"
    check.get_annotations.return_value = [ann]
    commit.get_check_runs.return_value = [check]

    result = get_pipeline_error_logs(pr, token="tkn")

    assert result["failed_checks"] == ["pytest"]
    assert "assert failed" in result["logs"]
    assert "app.py:10 NameError" in result["logs"]


def test_tail_job_log_filters_branch_fetch_noise():
    from src.agents.pr_assistant.pipeline import _tail_job_log

    raw = "\n".join(
        [
            "2026-01-01T00:00:00Z  * [new branch] feature-a -> origin/feature-a",
            "2026-01-01T00:00:01Z  * [new branch] feature-b -> origin/feature-b",
            "2026-01-01T00:00:02Z npm ERR! test failed",
        ]
    )

    result = _tail_job_log(raw)

    assert "new branch" not in result
    assert "npm ERR! test failed" in result
