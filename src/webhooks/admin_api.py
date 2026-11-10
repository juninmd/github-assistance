"""Authenticated admin API (`/api/*`) behind `Authorization: Bearer $ADMIN_API_TOKEN`.

Fail closed: without a configured token every route answers 403, because these
routes expose job history and act with the GitHub App's token.
"""

from __future__ import annotations

import hmac
from typing import Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, status

from src.agents.core.fleet import fleet_status
from src.config.settings import Settings
from src.queue.overview import MAX_WINDOW_HOURS, queue_overview
from src.webhooks.store import DeliveryStore

JobStatus = Literal["pending", "running", "succeeded", "failed", "blocked"]


def build_admin_router(app: FastAPI, config: Settings, store: DeliveryStore) -> APIRouter:
    def require_admin(authorization: str | None = Header(default=None)) -> None:
        token = config.admin_api_token
        if not token:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin API disabled")
        expected = f"Bearer {token}".encode()
        if not authorization or not hmac.compare_digest(authorization.encode(), expected):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "invalid token", headers={"WWW-Authenticate": "Bearer"}
            )

    router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])

    @router.get("/jobs")
    def list_jobs(
        status: JobStatus | None = None,
        repo: str | None = Query(default=None, max_length=200),
        q: str | None = Query(default=None, max_length=200),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        filters = {"status": status, "repo": repo, "search": q}
        return {
            "jobs": store.jobs.list_jobs(limit=limit, offset=offset, **filters),
            "total": store.jobs.count(**filters),
        }

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return _job_or_404(store, job_id)

    @router.post("/jobs/{job_id}/reprocess")
    def reprocess_job(job_id: str) -> dict[str, Any]:
        job = _job_or_404(store, job_id)
        if job["status"] == "running":
            raise HTTPException(status.HTTP_409_CONFLICT, "job is running")
        store.jobs.reprocess(job["kind"], job["key"])
        return _job_or_404(store, job_id)

    @router.get("/overview")
    def overview(hours: int = Query(default=24, ge=1, le=MAX_WINDOW_HOURS)) -> dict[str, Any]:
        worker = app.state.worker_thread
        return {
            **queue_overview(str(store.path), hours=hours),
            "deliveries": store.event_counts(hours),
            "service": {
                "mode": config.automation_mode,
                "simulation": config.simulation_mode,
                "worker_enabled": config.worker_enabled,
                "worker_alive": bool(worker and worker.is_alive()),
                "poll_interval_seconds": config.queue_poll_interval_seconds,
            },
        }

    @router.get("/agents")
    def agents() -> dict[str, Any]:
        return fleet_status(config)

    @router.get("/prs/{owner}/{repo}/{number}/explain")
    def pr_explain(owner: str, repo: str, number: int) -> dict[str, Any]:
        from src.insight.explain import explain_pr

        return explain_pr(config, f"{owner}/{repo}#{number}")

    return router


def _job_or_404(store: DeliveryStore, job_id: str) -> dict[str, Any]:
    job = store.jobs.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job
