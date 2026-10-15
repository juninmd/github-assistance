import subprocess
from unittest.mock import MagicMock, patch

from src.agents import opencode_models
from src.agents.opencode_local import run_opencode_task


def setup_function():
    opencode_models.reset_models_cache()


def test_get_free_opencode_models_prioritizes_deepseek():
    with patch("src.agents.opencode_models.proc_run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            ["opencode", "models"], 0, "m1-free\nopencode/deepseek-v4.1-flash-free\nm2-free\n", ""
        )
        models = opencode_models.get_free_opencode_models()
        assert models[0] == "opencode/deepseek-v4.1-flash-free"
        assert set(models) == {"m1-free", "opencode/deepseek-v4.1-flash-free", "m2-free"}


def test_select_free_opencode_model_respects_env(monkeypatch):
    monkeypatch.setenv("OPENCODE_MODEL", "custom/model")
    assert opencode_models.select_free_opencode_model(0) == "custom/model"
    assert opencode_models.select_free_opencode_model(1) == "custom/model"


def test_select_free_opencode_model_fallback(monkeypatch):
    with patch("src.agents.opencode_models.proc_run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            ["opencode", "models"], 0, "opencode/deepseek-v4.1-flash-free\nm2-free\n", ""
        )
        m0 = opencode_models.select_free_opencode_model(0)
        m1 = opencode_models.select_free_opencode_model(1)
        assert m0 == "opencode/deepseek-v4.1-flash-free"
        assert m1 == "m2-free"


@patch("src.agents.opencode_local._run_git")
@patch("src.agents.opencode_local.tempfile.TemporaryDirectory")
def test_run_opencode_task_retries_with_other_model(mock_tmp, _git, monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    mock_tmp.return_value.__enter__.return_value = str(tmp_path)
    _git.return_value = subprocess.CompletedProcess([], 0, "", "")

    def mock_proc(cmd, **_kwargs):
        if "models" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "opencode/deepseek-v4.1-flash-free\nm2-free\n", "")
        if "run" in cmd and "opencode/deepseek-v4.1-flash-free" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "quota error")
        if "run" in cmd and "m2-free" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "ok", "")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "M file.txt", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    github_client = MagicMock()
    pr = MagicMock()
    pr.assignees = []
    github_client.get_repo.return_value.create_pull.return_value = pr

    with patch("src.agents.opencode_local.proc_run", side_effect=mock_proc), \
         patch("src.agents.opencode_models.proc_run", side_effect=mock_proc):
        result = run_opencode_task(
            github_client=github_client,
            repository="owner/repo",
            instructions="do work",
            title="My Task",
            base_branch="main",
            log=MagicMock(),
        )

    assert result["status"] == "task_created"
    call_kwargs = github_client.get_repo.return_value.create_pull.call_args[1]
    assert "m2-free" in call_kwargs["body"]
