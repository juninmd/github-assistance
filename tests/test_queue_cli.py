"""Queue CLI + PR webhook handler (observe mode, no external effects)."""

from unittest.mock import MagicMock, patch

from src.config.settings import Settings
from src.queue.store import JobStore
from src.webhooks.dispatcher import make_pr_handler


def _settings(tmp_path) -> Settings:
    return Settings(github_token="token", webhook_database_path=str(tmp_path / "queue.db"))


def test_pr_handler_observe_mode_no_external_effects(tmp_path):
    settings = _settings(tmp_path)
    settings.automation_mode = "observe"
    handler = make_pr_handler(settings)
    job = {"id": "x", "key": "juninmd/repo#1", "payload": {"mode": "observe"}}
    outcome = handler(job)
    assert outcome["status"] == "succeeded"
    assert outcome["decision"] == "observed"
    assert outcome["result"] == {"action": "observed"}


def test_pr_handler_autonomous_failure_records_error(tmp_path):
    settings = _settings(tmp_path)
    settings.automation_mode = "autonomous"
    handler = make_pr_handler(settings)
    job = {"id": "x", "key": "juninmd/repo#2", "payload": {"mode": "autonomous"}}
    with patch(
        "src.webhooks.dispatcher.run_agent",
        return_value={"error": "boom", "_run_result": {"status": "failed"}},
    ):
        outcome = handler(job)
    assert outcome["status"] == "failed"
    assert outcome["error"] == "boom"


def test_queue_cli_reprocess(tmp_path, capsys):
    from src.queue.cli import cmd_reprocess

    settings = _settings(tmp_path)
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    store.enqueue("pr", "juninmd/repo#3", {"mode": "observe"})
    store.complete(store.list_jobs()[0]["id"], "succeeded")

    with patch("src.queue.cli.Settings.from_env", return_value=settings):
        args = MagicMock(pr="juninmd/repo#3")
        cmd_reprocess(args)
    out = capsys.readouterr().out
    assert "reprocess ok" in out
    assert store.list_jobs()[0]["status"] == "pending"
