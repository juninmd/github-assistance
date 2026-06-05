from unittest.mock import MagicMock, patch

from src.agents.pr_assistant import pipeline_fixer
from src.agents.pr_assistant.pipeline_fixer import (
    build_marker,
    fix_pipeline_autonomously,
    max_attempts,
    pipeline_fix_enabled,
    read_attempt_state,
)


def _comment(body: str) -> MagicMock:
    c = MagicMock()
    c.body = body
    return c


def test_pipeline_fix_enabled_toggle(monkeypatch):
    monkeypatch.delenv("PIPELINE_FIX_ENABLED", raising=False)
    assert pipeline_fix_enabled() is False
    monkeypatch.setenv("PIPELINE_FIX_ENABLED", "true")
    assert pipeline_fix_enabled() is True


def test_max_attempts_default_and_override(monkeypatch):
    monkeypatch.delenv("PIPELINE_FIX_MAX_ATTEMPTS", raising=False)
    assert max_attempts() == 3
    monkeypatch.setenv("PIPELINE_FIX_MAX_ATTEMPTS", "5")
    assert max_attempts() == 5
    monkeypatch.setenv("PIPELINE_FIX_MAX_ATTEMPTS", "garbage")
    assert max_attempts() == 3


def test_read_attempt_state_uses_latest_marker():
    comments = [
        _comment("first " + build_marker(1, "aaa111")),
        _comment("no marker here"),
        _comment("second " + build_marker(2, "bbb222")),
    ]
    attempt, sha = read_attempt_state(comments)
    assert attempt == 2
    assert sha == "bbb222"


def test_read_attempt_state_no_marker():
    assert read_attempt_state([_comment("nothing")]) == (0, "")


def test_fix_pipeline_skips_when_no_logs():
    pr = MagicMock()
    ok, msg, sha = fix_pipeline_autonomously(pr, "   ", [], 1, 3)
    assert ok is False
    assert "No pipeline error logs" in msg
    assert sha == ""


def test_fix_pipeline_skips_fork():
    pr = MagicMock()
    pr.head.repo.full_name = "contributor/fork"
    pr.base.repo.full_name = "owner/repo"
    ok, msg, sha = fix_pipeline_autonomously(pr, "boom error", ["test"], 1, 3)
    assert ok is False
    assert "fork" in msg.lower()


def _same_repo_pr():
    pr = MagicMock()
    pr.head.repo.full_name = "owner/repo"
    pr.base.repo.full_name = "owner/repo"
    pr.head.ref = "feature"
    return pr


@patch("src.agents.pr_assistant.pipeline_fixer._setup_clone_environment", return_value="/tmp/repo")
@patch("src.agents.pr_assistant.pipeline_fixer._run_git")
@patch("src.agents.pr_assistant.pipeline_fixer._run_opencode_fix", return_value="opencode/m-free")
@patch("src.agents.pr_assistant.pipeline_fixer._changed_files")
@patch("src.agents.pr_assistant.pipeline_fixer._validate_changes", return_value=(True, "checks"))
def test_fix_pipeline_success_pushes(
    mock_validate, mock_changed, mock_opencode, mock_git, mock_clone, monkeypatch
):
    monkeypatch.setenv("GITHUB_TOKEN", "tkn")
    mock_changed.return_value = ["app.py"]
    mock_git.return_value = MagicMock(stdout="newsha123\n")
    pr = _same_repo_pr()

    ok, msg, sha = fix_pipeline_autonomously(pr, "TypeError boom", ["test"], 2, 3)

    assert ok is True
    assert sha == "newsha123"
    assert "attempt 2/3" in msg
    assert "app.py" in msg
    # commit + push happened
    pushed = any("push" in call.args[0] for call in mock_git.call_args_list)
    assert pushed


@patch("src.agents.pr_assistant.pipeline_fixer._setup_clone_environment", return_value="/tmp/repo")
@patch("src.agents.pr_assistant.pipeline_fixer._run_git")
@patch("src.agents.pr_assistant.pipeline_fixer._run_opencode_fix", return_value="opencode/m-free")
@patch("src.agents.pr_assistant.pipeline_fixer._changed_files", return_value=[])
def test_fix_pipeline_fails_when_no_changes(
    mock_changed, mock_opencode, mock_git, mock_clone, monkeypatch
):
    monkeypatch.setenv("GITHUB_TOKEN", "tkn")
    pr = _same_repo_pr()
    ok, msg, sha = fix_pipeline_autonomously(pr, "boom", ["test"], 1, 3)
    assert ok is False
    assert "no file changes" in msg
    assert sha == ""


@patch("src.agents.pr_assistant.pipeline_fixer._setup_clone_environment", return_value="/tmp/repo")
@patch("src.agents.pr_assistant.pipeline_fixer._run_git")
@patch("src.agents.pr_assistant.pipeline_fixer._run_opencode_fix", return_value="")
def test_fix_pipeline_fails_when_opencode_silent(mock_oc, mock_git, mock_clone, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tkn")
    pr = _same_repo_pr()
    ok, msg, _ = fix_pipeline_autonomously(pr, "boom", ["test"], 1, 3)
    assert ok is False
    assert "did not produce" in msg
