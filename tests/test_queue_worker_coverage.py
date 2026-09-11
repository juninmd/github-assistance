"""Coverage for queue worker/CLI, webhook API endpoints and insight CLI."""

import json
import threading
from unittest.mock import MagicMock, patch

from src.config.settings import Settings
from src.queue.store import JobStore
from src.queue.worker import QueueWorker

_ADMIN = "admin"


def _settings(tmp_path) -> Settings:
    return Settings(github_token="token", webhook_database_path=str(tmp_path / "queue.db"))


def test_worker_run_until_empty_and_handler_exception(tmp_path):
    store = JobStore(str(tmp_path / "q.db"))
    store.initialize()
    store.enqueue("pr", "juninmd/repo#1", {}, now=1.0)
    store.enqueue("pr", "juninmd/repo#2", {}, now=1.0)

    def handler(job):
        if job["key"] == "juninmd/repo#1":
            raise RuntimeError("boom")
        return {"status": "succeeded"}

    worker = QueueWorker(store, handler, clock=lambda: 2.0)
    processed = worker.run_until_empty(now=2.0)
    assert processed == 2
    by_key = {j["key"]: j["status"] for j in store.list_jobs()}
    assert by_key["juninmd/repo#1"] == "pending"  # retryable failure
    assert by_key["juninmd/repo#2"] == "succeeded"


def test_worker_unknown_status_treated_as_failed(tmp_path):
    store = JobStore(str(tmp_path / "q.db"))
    store.initialize()
    store.enqueue("pr", "juninmd/repo#3", {}, now=1.0)
    worker = QueueWorker(store, lambda _j: {"status": "nonsense"}, clock=lambda: 2.0)
    worker.run_once(now=2.0)
    job = store.list_jobs()[0]
    assert job["status"] in ("pending", "blocked")
    assert job["last_error"] == "unknown status: nonsense"


def test_worker_run_stops_on_event(tmp_path):
    store = JobStore(str(tmp_path / "q.db"))
    store.initialize()
    stop = threading.Event()
    stop.set()
    worker = QueueWorker(store, lambda _j: {"status": "succeeded"}, stop=stop, clock=lambda: 2.0)
    worker.run(poll_interval=0.01)  # exits immediately because stop is set


def test_queue_cli_list_and_stats(tmp_path, capsys):
    from src.queue.cli import cmd_list, cmd_stats

    settings = _settings(tmp_path)
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    store.enqueue("pr", "juninmd/repo#4", {}, now=1.0)

    with patch("src.queue.cli.Settings.from_env", return_value=settings):
        cmd_list(MagicMock(status=None, limit=100, json=True))
        out = capsys.readouterr().out
        assert json.loads(out)["jobs"][0]["key"] == "juninmd/repo#4"

        cmd_list(MagicMock(status="pending", limit=100, json=False))
        assert "juninmd/repo#4" in capsys.readouterr().out

        cmd_stats(MagicMock(json=True))
        assert "pending" in capsys.readouterr().out


def test_queue_cli_worker_once(tmp_path, capsys):
    from src.queue.cli import cmd_worker

    settings = _settings(tmp_path)
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    store.enqueue("pr", "juninmd/repo#5", {"mode": "observe"}, now=1.0)

    with patch("src.queue.cli.Settings.from_env", return_value=settings):
        cmd_worker(MagicMock(once=True, observe=True))
    assert "processed=" in capsys.readouterr().out


def test_webhook_api_jobs_and_explain(tmp_path):
    from fastapi.testclient import TestClient

    from src.webhooks.server import create_app

    settings = _settings(tmp_path)
    settings.worker_enabled = False
    settings.admin_api_token = _ADMIN
    auth = {"Authorization": f"Bearer {_ADMIN}"}
    app = create_app(settings)
    store = app.state.store
    store.initialize()
    store.record_and_enqueue(
        "delivery-api", "pull_request", {"repository": {"full_name": "juninmd/repo"}},
        ["juninmd/repo#6"], mode="observe",
    )
    with TestClient(app) as client:
        jobs = client.get("/api/jobs", headers=auth).json()["jobs"]
        assert jobs[0]["key"] == "juninmd/repo#6"

        with patch("src.insight.explain.explain_pr", return_value={"reasons": ["checks_pending"]}) as mock_explain:
            resp = client.get("/api/prs/juninmd/repo/6/explain", headers=auth)
        assert resp.json()["reasons"] == ["checks_pending"]
        mock_explain.assert_called_once()

        assert client.get("/health/live").json()["status"] == "ok"


def test_insight_cli_history(tmp_path, capsys):
    from src.insight.cli import main

    settings = _settings(tmp_path)
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    store.enqueue("pr", "juninmd/repo#8", {"mode": "observe"}, now=1.0)

    with (
        patch("src.insight.cli.Settings.from_env", return_value=settings),
        patch("sys.argv", ["pr-insight", "history", "--pr", "juninmd/repo#8", "--json"]),
    ):
        main()
    out = capsys.readouterr().out
    assert "juninmd/repo#8" in json.loads(out)["history"][0]["key"]
