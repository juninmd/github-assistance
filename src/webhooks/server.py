"""HTTP entrypoint for GitHub App webhooks (durable queue worker)."""

from __future__ import annotations

import json
import threading
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, status

from src.config.settings import Settings
from src.queue.store import JobStore
from src.queue.worker import QueueWorker
from src.utils.logger import get_logger
from src.webhooks.auth import GitHubAppAuth, valid_signature
from src.webhooks.dispatcher import extract_pr_refs, make_pr_handler
from src.webhooks.store import DeliveryStore

MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
SUPPORTED_EVENTS = {
    "check_suite",
    "issue_comment",
    "pull_request",
    "pull_request_review",
    "workflow_run",
}
_log = get_logger("webhook-server")


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    store = DeliveryStore(config.webhook_database_path)
    app = FastAPI(title="GitHub Assistance Webhooks")
    app.state.settings = config
    app.state.store = store
    app.state.worker_thread = None
    app.state.worker_stop = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        store.initialize()
        if config.worker_enabled:
            stop = threading.Event()
            worker = QueueWorker(
                JobStore(config.webhook_database_path),
                make_pr_handler(config),
                stop=stop,
            )
            thread = threading.Thread(
                target=worker.run,
                kwargs={"poll_interval": config.queue_poll_interval_seconds},
                name="queue-worker",
                daemon=True,
            )
            thread.start()
            app.state.worker_thread = thread
            app.state.worker_stop = stop
            _log.info("Durable queue worker started", db=str(config.webhook_database_path))
        yield
        stop = app.state.worker_stop
        if stop:
            stop.set()
        thread = app.state.worker_thread
        if thread and thread.is_alive():
            thread.join(timeout=5)

    app.router.lifespan_context = lifespan

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        if not _configured(config) or not store.ready():
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "service not ready")
        return {"status": "ready", "mode": config.automation_mode}

    @app.get("/api/jobs")
    def list_jobs(status: str | None = None, limit: int = 100) -> dict[str, Any]:
        return {"jobs": store.jobs.list_jobs(status=status, limit=limit)}

    @app.get("/api/prs/{owner}/{repo}/{number}/explain")
    def pr_explain(owner: str, repo: str, number: int) -> dict[str, Any]:
        from src.insight.explain import explain_pr

        return explain_pr(config, f"{owner}/{repo}#{number}")

    @app.post("/webhooks/github")
    async def github_webhook(
        request: Request,
        x_github_delivery: str | None = Header(default=None),
        x_github_event: str | None = Header(default=None),
        x_hub_signature_256: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not x_github_delivery or not x_github_event:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing GitHub headers")
        body = await request.body()
        if len(body) > MAX_PAYLOAD_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "payload too large")
        if not config.github_webhook_secret or not valid_signature(
            body, x_hub_signature_256, config.github_webhook_secret
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid signature")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid JSON") from exc
        if x_github_event not in SUPPORTED_EVENTS:
            return {"accepted": False, "reason": "unsupported_event"}
        pr_refs = extract_pr_refs(x_github_event, payload)
        if x_github_event == "issue_comment" and payload.get("sender", {}).get("type") == "Bot":
            pr_refs = []
        created, _job_ids = store.record_and_enqueue(
            x_github_delivery,
            x_github_event,
            payload,
            pr_refs,
            mode=config.automation_mode,
        )
        _log.info(
            "Webhook persisted",
            delivery=x_github_delivery,
            event=x_github_event,
            duplicate=not created,
        )
        return {
            "accepted": True,
            "duplicate": not created,
            "mode": config.automation_mode,
            "pr_refs": pr_refs,
        }

    return app


def _configured(settings: Settings) -> bool:
    app_id = settings.github_app_id
    installation_id = settings.github_installation_id
    key_path = settings.github_app_private_key_path
    if not app_id or not installation_id or not key_path or not settings.github_webhook_secret:
        return False
    try:
        GitHubAppAuth(app_id, installation_id, key_path).jwt()
    except (OSError, ValueError):
        return False
    return True


def main() -> None:
    uvicorn.run(
        "src.webhooks.server:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - container service must accept pod traffic
        port=8080,
    )
