from unittest.mock import MagicMock, patch

from src.agents.conflict_resolver.agent import ConflictResolverAgent


def _agent() -> ConflictResolverAgent:
    agent = ConflictResolverAgent(
        github_client=MagicMock(),
        jules_client=MagicMock(),
        telegram=MagicMock(),
        allowlist=MagicMock(),
        target_owner="juninmd",
    )
    agent.telegram.escape_html = lambda value: value
    return agent


@patch("src.agents.conflict_resolver.agent.resolve_conflicts_autonomously")
def test_process_conflict_failure_marks_manual_without_closing(mock_resolve):
    agent = _agent()
    pr = MagicMock()
    pr.number = 123
    pr.user.login = "dependabot[bot]"
    pr.base.repo.full_name = "owner/repo"
    pr.html_url = "https://github.com/owner/repo/pull/123"
    pr.title = "Update dependency"
    results = {"resolved": [], "manual": []}
    mock_resolve.return_value = (False, "Unresolved conflict files remain: package.json")
    agent.github_client.add_label_to_pr.return_value = (True, "label added")

    agent._process_conflict(pr, results)

    assert results["resolved"] == []
    assert results["manual"] == [
        {"pr": 123, "repo": "owner/repo", "error": "Unresolved conflict files remain: package.json"}
    ]
    agent.github_client.comment_on_pr.assert_called_once()
    agent.github_client.add_label_to_pr.assert_called_once_with(
        pr, ConflictResolverAgent.MANUAL_CONFLICT_LABEL
    )
    pr.edit.assert_not_called()


def _pipeline_pr() -> MagicMock:
    pr = MagicMock()
    pr.number = 7
    pr.user.login = "renovate[bot]"
    pr.base.repo.full_name = "owner/repo"
    pr.head.sha = "headsha"
    pr.html_url = "https://github.com/owner/repo/pull/7"
    pr.title = "Bump dep"
    return pr


@patch("src.agents.conflict_resolver.agent.fix_pipeline_autonomously")
@patch("src.agents.conflict_resolver.agent.get_pipeline_error_logs")
@patch("src.agents.conflict_resolver.agent.check_pipeline_status")
def test_pipeline_fix_success_comments_and_records(mock_status, mock_logs, mock_fix):
    agent = _agent()
    pr = _pipeline_pr()
    mock_status.return_value = {"state": "failure"}
    mock_logs.return_value = {"logs": "TypeError boom", "failed_checks": ["test"]}
    mock_fix.return_value = (True, "Pushed pipeline fix (attempt 1/3)", "newsha")
    agent.github_client.get_issue_comments.return_value = []
    results = {"pipeline_fixed": [], "pipeline_manual": []}

    agent._maybe_fix_pipeline(pr, results)

    assert results["pipeline_fixed"] == [
        {"pr": 7, "repo": "owner/repo", "msg": "Pushed pipeline fix (attempt 1/3)"}
    ]
    # marker comment carries the next attempt + pushed sha
    body = agent.github_client.comment_on_pr.call_args.args[1]
    assert "<!-- pipeline-fix attempt=1 sha=newsha -->" in body


@patch("src.agents.conflict_resolver.agent.fix_pipeline_autonomously")
@patch("src.agents.conflict_resolver.agent.get_pipeline_error_logs")
@patch("src.agents.conflict_resolver.agent.check_pipeline_status")
def test_pipeline_fix_exhausted_marks_manual(mock_status, mock_logs, mock_fix, monkeypatch):
    monkeypatch.setenv("PIPELINE_FIX_MAX_ATTEMPTS", "3")
    agent = _agent()
    pr = _pipeline_pr()
    pr.as_issue.return_value.labels = []
    mock_status.return_value = {"state": "failure"}
    prior = MagicMock()
    prior.body = "Tentativa 3/3 <!-- pipeline-fix attempt=3 sha=abc -->"
    agent.github_client.get_issue_comments.return_value = [prior]
    agent.github_client.add_label_to_pr.return_value = (True, "ok")
    results = {"pipeline_fixed": [], "pipeline_manual": []}

    agent._maybe_fix_pipeline(pr, results)

    mock_fix.assert_not_called()
    agent.github_client.add_label_to_pr.assert_called_once_with(
        pr, "needs-manual-pipeline-fix"
    )


@patch("src.agents.conflict_resolver.agent.check_pipeline_status")
def test_pipeline_fix_skipped_when_pipeline_healthy(mock_status):
    agent = _agent()
    pr = _pipeline_pr()
    mock_status.return_value = {"state": "success"}
    results = {"pipeline_fixed": [], "pipeline_manual": []}

    agent._maybe_fix_pipeline(pr, results)

    agent.github_client.comment_on_pr.assert_not_called()
    agent.github_client.add_label_to_pr.assert_not_called()
