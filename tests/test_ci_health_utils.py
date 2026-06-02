from unittest.mock import MagicMock

from src.agents.ci_health.utils import remediate_pipeline


def test_remediate_pipeline_creates_vibe_code_opencode_task():
    agent = MagicMock()
    repo = MagicMock()
    repo.full_name = "owner/repo"
    agent.create_vibe_code_opencode_task.return_value = {"status": "task_created", "task_id": "t1", "task_url": "http://localhost:3000/tasks/t1"}
    failures = [{"name": "CI", "conclusion": "failure", "url": "https://github.com/run/1"}]

    result = remediate_pipeline(agent, repo, failures)

    assert result == {
        "repository": "owner/repo",
        "status": "task_created",
        "task_id": "t1",
        "task_url": "http://localhost:3000/tasks/t1",
    }
    agent.create_vibe_code_opencode_task.assert_called_once()


def test_remediate_pipeline_returns_failure_status_when_vibe_code_fails():
    agent = MagicMock()
    repo = MagicMock()
    repo.full_name = "owner/repo"
    agent.create_vibe_code_opencode_task.return_value = {"status": "vibe_code_failed", "error": "boom"}
    failures = [{"name": "CI", "conclusion": "failure", "url": "https://github.com/run/1"}]

    result = remediate_pipeline(agent, repo, failures)

    assert result == {
        "repository": "owner/repo",
        "status": "vibe_code_failed",
        "error": "boom",
    }


def test_remediate_pipeline_returns_none_when_opencode_raises():
    agent = MagicMock()
    repo = MagicMock()
    repo.full_name = "owner/repo"
    agent.create_vibe_code_opencode_task.side_effect = RuntimeError("unexpected")
    failures = [{"name": "CI", "conclusion": "failure", "url": "https://github.com/run/1"}]

    result = remediate_pipeline(agent, repo, failures)

    assert result is None
    agent.log.assert_called_once_with(
        "Failed opencode remediation in owner/repo: unexpected",
        "WARNING",
    )
