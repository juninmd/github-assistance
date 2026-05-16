from unittest.mock import MagicMock

from src.agents.ci_health.utils import remediate_pipeline


def test_remediate_pipeline_opens_pr_with_opencode():
    agent = MagicMock()
    repo = MagicMock()
    repo.full_name = "owner/repo"
    agent.run_opencode_on_repo.return_value = {
        "status": "success",
        "pr_url": "https://github.com/owner/repo/pull/123",
        "branch": "agent/fix-ci",
    }
    failures = [{"name": "CI", "conclusion": "failure", "url": "https://github.com/run/1"}]

    result = remediate_pipeline(agent, repo, failures)

    assert result == {
        "repository": "owner/repo",
        "status": "pr_opened",
        "pr_url": "https://github.com/owner/repo/pull/123",
        "branch": "agent/fix-ci",
    }
    agent.run_opencode_on_repo.assert_called_once()


def test_remediate_pipeline_returns_failure_status_when_opencode_fails():
    agent = MagicMock()
    repo = MagicMock()
    repo.full_name = "owner/repo"
    agent.run_opencode_on_repo.return_value = {"status": "opencode_failed", "stderr": "boom"}
    failures = [{"name": "CI", "conclusion": "failure", "url": "https://github.com/run/1"}]

    result = remediate_pipeline(agent, repo, failures)

    assert result == {
        "repository": "owner/repo",
        "status": "opencode_failed",
        "error": "boom",
    }
