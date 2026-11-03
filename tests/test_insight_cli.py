"""Tests for src/insight/cli.py covering explain, history, formatting, and main entrypoint."""

import json
from unittest.mock import patch

from src.config.settings import Settings
from src.insight.cli import _emit, main
from src.queue.store import JobStore


def _settings(tmp_path) -> Settings:
    return Settings(github_token="token", webhook_database_path=str(tmp_path / "queue.db"))


def test_insight_cli_explain_json(tmp_path, capsys):
    settings = _settings(tmp_path)
    mock_result = {
        "pr_ref": "o/r#1",
        "state": "open",
        "merged": False,
        "autonomy_mode": "merge",
        "pipeline_state": "pending",
        "reasons": ["checks_pending"],
    }
    with (
        patch("src.insight.cli.Settings.from_env", return_value=settings),
        patch("src.insight.cli.explain_pr", return_value=mock_result),
        patch("sys.argv", ["pr-insight", "explain", "--pr", "o/r#1", "--json"]),
    ):
        main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["pr_ref"] == "o/r#1"
    assert data["reasons"] == ["checks_pending"]


def test_insight_cli_explain_text(tmp_path, capsys):
    settings = _settings(tmp_path)
    mock_result = {
        "pr_ref": "o/r#2",
        "state": "open",
        "merged": False,
        "autonomy_mode": "observe",
        "pipeline_state": "success",
        "reasons": ["no_reasons_found"],
    }
    with (
        patch("src.insight.cli.Settings.from_env", return_value=settings),
        patch("src.insight.cli.explain_pr", return_value=mock_result),
        patch("sys.argv", ["pr-insight", "explain", "--pr", "o/r#2"]),
    ):
        main()
    out = capsys.readouterr().out
    assert "PR: o/r#2" in out
    assert "state=open" in out
    assert "autonomy=observe" in out
    assert "- no_reasons_found" in out


def test_insight_cli_history_text_and_json(tmp_path, capsys):
    settings = _settings(tmp_path)
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    store.enqueue("pr", "o/r#3", {"mode": "observe"}, now=100.0)

    # Test text output
    with (
        patch("src.insight.cli.Settings.from_env", return_value=settings),
        patch("sys.argv", ["pr-insight", "history", "--pr", "o/r#3"]),
    ):
        main()
    out = capsys.readouterr().out
    assert "pending" in out
    assert "o/r#3" in out

    # Test JSON output
    with (
        patch("src.insight.cli.Settings.from_env", return_value=settings),
        patch("sys.argv", ["pr-insight", "history", "--pr", "o/r#3", "--json"]),
    ):
        main()
    out_json = capsys.readouterr().out
    data = json.loads(out_json)
    assert len(data["history"]) == 1
    assert data["history"][0]["key"] == "o/r#3"


def test_emit_direct(capsys):
    res = {
        "pr_ref": "o/r#4",
        "state": "closed",
        "merged": True,
        "autonomy_mode": "merge",
        "pipeline_state": "success",
        "reasons": ["already_merged"],
    }
    _emit(res, raw_json=True)
    out_json = capsys.readouterr().out
    assert json.loads(out_json)["pr_ref"] == "o/r#4"

    _emit(res, raw_json=False)
    out_text = capsys.readouterr().out
    assert "PR: o/r#4" in out_text
    assert "- already_merged" in out_text


def test_main_dunder_entry(tmp_path):
    import runpy

    settings = _settings(tmp_path)
    with (
        patch("sys.argv", ["pr-insight", "explain", "--pr", "o/r#1", "--json"]),
        patch("src.insight.cli.explain_pr", return_value={"pr_ref": "o/r#1"}),
        patch("src.insight.cli.Settings.from_env", return_value=settings),
    ):
        runpy.run_module("src.insight.cli", run_name="__main__")
