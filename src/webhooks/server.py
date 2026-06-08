"""HTTP entrypoint for GitHub App webhooks."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, status

from src.config.settings import Settings
from src.utils.logger import get_logger
from src.webhooks.auth import GitHubAppAuth, valid_signature
from src.webhooks.dispatcher import enqueue_pr, extract_pr_refs
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

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        store.initialize()
        yield

    app = FastAPI(title="GitHub Assistance Webhooks", lifespan=lifespan)
    app.state.settings = config
    app.state.store = store

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        if not _configured(config) or not store.ready():
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "service not ready")
        return {"status": "ready", "mode": config.automation_mode}

    @app.post("/webhooks/github")
    async def github_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
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
        created = store.record(x_github_delivery, x_github_event, payload)
        pr_refs = extract_pr_refs(x_github_event, payload)
        if x_github_event == "issue_comment" and payload.get("sender", {}).get("type") == "Bot":
            pr_refs = []
        if created and config.automation_mode == "autonomous":
            for pr_ref in pr_refs:
                background_tasks.add_task(enqueue_pr, config, pr_ref)
        _log.info(
            "Webhook observed",
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
