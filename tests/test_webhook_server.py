import hashlib
import hmac
from pathlib import Path

from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.webhooks.server import create_app


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        github_token="unused",
        github_app_id=3982807,
        github_installation_id=138493700,
        github_app_private_key_path=str(tmp_path / "missing.pem"),
        github_webhook_secret="test-secret",
        webhook_database_path=str(tmp_path / "webhooks.db"),
        worker_enabled=False,
    )


def _signature(body: bytes) -> str:
    digest = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_webhook_records_and_deduplicates(tmp_path):
    app = create_app(_settings(tmp_path))
    body = (
        b'{"action":"opened","number":1,"pull_request":{"number":1},'
        b'"repository":{"full_name":"juninmd/repo"}}'
    )
    headers = {
        "X-GitHub-Delivery": "delivery-1",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": _signature(body),
        "Content-Type": "application/json",
    }
    with TestClient(app) as client:
        first = client.post("/webhooks/github", content=body, headers=headers)
        second = client.post("/webhooks/github", content=body, headers=headers)
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert first.json()["pr_refs"] == ["juninmd/repo#1"]


def test_webhook_rejects_invalid_signature(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/webhooks/github",
            content=b"{}",
            headers={
                "X-GitHub-Delivery": "delivery-2",
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )
    assert response.status_code == 401


def test_unsupported_event_is_ignored(tmp_path):
    app = create_app(_settings(tmp_path))
    body = b"{}"
    with TestClient(app) as client:
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Delivery": "delivery-3",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": _signature(body),
            },
        )
    assert response.json() == {"accepted": False, "reason": "unsupported_event"}


def test_autonomous_mode_persists_targeted_pr_job(tmp_path):
    settings = _settings(tmp_path)
    settings.automation_mode = "autonomous"
    app = create_app(settings)
    body = (
        b'{"action":"opened","number":8,"pull_request":{"number":8},'
        b'"repository":{"full_name":"juninmd/repo"}}'
    )
    with TestClient(app) as client:
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Delivery": "delivery-autonomous",
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": _signature(body),
            },
        )
    assert response.status_code == 200
    jobs = app.state.store.jobs.list_jobs()
    assert [j["key"] for j in jobs] == ["juninmd/repo#8"]
    assert jobs[0]["payload"]["mode"] == "autonomous"


def test_webhook_job_survives_worker_restart(tmp_path):
    """Webhook persisted -> job pending; crashed worker lease recovered on restart."""
    import time as _time

    from src.queue.store import JobStore
    from src.queue.worker import QueueWorker

    settings = _settings(tmp_path)
    settings.automation_mode = "observe"
    app = create_app(settings)
    body = (
        b'{"action":"opened","number":21,"pull_request":{"number":21},'
        b'"repository":{"full_name":"juninmd/repo"}}'
    )
    with TestClient(app) as client:
        client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Delivery": "delivery-restart",
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": _signature(body),
            },
        )
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    jobs = store.list_jobs()
    assert len(jobs) == 1 and jobs[0]["status"] == "pending"

    # A worker claims the job then "crashes" before completing.
    now = _time.time()
    claimed = store.claim(now=now)
    assert claimed[0]["status"] == "running"

    # Restart: stale lease is recovered and the job is processed exactly once.
    seen = []

    def handler(job):
        seen.append(job["id"])
        return {"status": "succeeded", "decision": "observed", "next_action": "observe"}

    QueueWorker(store, handler).run_once(now=now + 301)
    assert seen == [claimed[0]["id"]]
    assert store.list_jobs()[0]["status"] == "succeeded"


def test_webhook_event_during_processing_marks_reevaluation(tmp_path):
    import time as _time

    settings = _settings(tmp_path)
    app = create_app(settings)
    body = (
        b'{"action":"synchronize","number":31,"pull_request":{"number":31},'
        b'"repository":{"full_name":"juninmd/repo"}}'
    )
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": _signature(body),
    }
    with TestClient(app) as client:
        client.post(
            "/webhooks/github",
            content=body,
            headers={**headers, "X-GitHub-Delivery": "delivery-31a"},
        )
    store = app.state.store.jobs
    store.claim(now=_time.time())  # a worker is processing this PR right now

    with TestClient(app) as client:
        client.post(
            "/webhooks/github",
            content=body,
            headers={**headers, "X-GitHub-Delivery": "delivery-31b"},
        )
    jobs = store.list_jobs()
    assert len(jobs) == 1  # coalesced, not duplicated
    assert jobs[0]["reprocess_pending"] is True


def test_observe_mode_job_processed_without_external_effects(tmp_path):
    from src.queue.worker import QueueWorker

    settings = _settings(tmp_path)
    settings.automation_mode = "observe"
    app = create_app(settings)
    body = (
        b'{"action":"opened","number":41,"pull_request":{"number":41},'
        b'"repository":{"full_name":"juninmd/repo"}}'
    )
    with TestClient(app) as client:
        client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Delivery": "delivery-observe",
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": _signature(body),
            },
        )
    store = app.state.store.jobs
    QueueWorker(store, lambda _j: {"status": "succeeded", "decision": "observed"}).run_once()
    job = store.list_jobs()[0]
    assert job["status"] == "succeeded"
    assert job["decision"] == "observed"


def test_record_and_enqueue_is_atomic(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    store = app.state.store
    store.initialize()
    created, job_ids = store.record_and_enqueue(
        "delivery-atomic", "pull_request", {"repository": {"full_name": "juninmd/repo"}}, ["juninmd/repo#51"],
        mode="observe",
    )
    assert created is True
    assert len(job_ids) == 1
    assert store.jobs.get(job_ids[0])["status"] == "pending"


def test_bot_issue_comment_does_not_enqueue_job(tmp_path):
    settings = _settings(tmp_path)
    settings.automation_mode = "autonomous"
    app = create_app(settings)
    body = (
        b'{"action":"created","issue":{"number":8,"pull_request":{"url":"pr"}},'
        b'"sender":{"type":"Bot"},"repository":{"full_name":"juninmd/repo"}}'
    )
    with TestClient(app) as client:
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Delivery": "delivery-bot-comment",
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": _signature(body),
            },
        )
    assert response.status_code == 200
    assert response.json()["pr_refs"] == []
    assert app.state.store.jobs.list_jobs() == []
