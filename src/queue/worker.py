"""Queue worker: claims durable jobs, runs a handler, records outcomes.

The worker recovers stale leases on every cycle (restart safety), runs at most
``limit`` jobs per poll (bounded simultaneous work), and never duplicates
effects because claiming is atomic and handlers are expected to be idempotent.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from src.queue.store import JobStore
from src.utils.logger import get_logger

_log = get_logger("queue-worker")


class QueueWorker:
    """Poll the JobStore and process due jobs through ``handle``."""

    def __init__(
        self,
        store: JobStore,
        handle: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        lease_seconds: int = 300,
        backoff_seconds: int = 60,
        limit: int = 1,
        clock: Callable[[], float] = time.time,
        stop: threading.Event | None = None,
    ) -> None:
        self.store = store
        self.handle = handle
        self.lease_seconds = lease_seconds
        self.backoff_seconds = backoff_seconds
        self.limit = limit
        self._clock = clock
        self._stop = stop or threading.Event()
        self._lease_delta = lease_seconds

    def run_once(self, now: float | None = None) -> list[dict[str, Any]]:
        """Recover stale leases, claim due jobs and process them."""
        now = now if now is not None else self._clock()
        self.store.recover_stale(now)
        jobs = self.store.claim(now, limit=self.limit)
        outcomes: list[dict[str, Any]] = []
        for job in jobs:
            outcomes.append(self._process(job, now))
        return outcomes

    def _process(self, job: dict[str, Any], now: float) -> dict[str, Any]:
        try:
            outcome = self.handle(job) or {}
        except Exception as exc:  # noqa: BLE001 - worker must never die silently
            _log.error("job handler failed", job=job["id"], error=str(exc))
            outcome = {"status": "failed", "error": str(exc)}
        status = outcome.get("status", "failed")
        if status not in ("succeeded", "failed", "blocked"):
            _log.warning(
                "handler returned unknown status; treating as failed",
                job=job["id"], status=status,
            )
            status = "failed"
            outcome["error"] = outcome.get("error") or f"unknown status: {status}"
        return self.store.complete(
            job["id"],
            status,
            error=outcome.get("error"),
            decision=outcome.get("decision"),
            next_action=outcome.get("next_action"),
            sha=outcome.get("sha"),
            task_id=outcome.get("task_id"),
            now=now,
            backoff_seconds=self.backoff_seconds,
        )

    def run_until_empty(self, now: float | None = None) -> int:
        """Drain all due jobs (used by ``--once``/Kubernetes Job execution)."""
        processed = 0
        while self.run_once(now):
            processed += 1
            now = None
            if self._stop.is_set():
                break
        return processed

    def run(self, poll_interval: float = 15) -> None:
        """Run until the stop event is set (daemon/web server loop)."""
        while not self._stop.wait(poll_interval):
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                _log.error("worker cycle failed", error=str(exc))


def make_observer_handler() -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Handler that records observations without any external effect."""

    def handle(_job: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "succeeded",
            "decision": "observed",
            "next_action": "observe",
            "result": {"action": "observed"},
        }

    return handle
