"""SQLite-backed durable job queue with leases, retries and idempotency.

Single-writer design: one row per (kind, key). New events coalesce into the
existing job and set ``reprocess_pending`` so the worker re-evaluates after the
current run completes. Restart recovery resets expired or orphaned leases to
``pending``.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from src.queue.outcome import complete_job, reprocess_job
from src.queue.read import get_job, job_stats, list_jobs
from src.queue.schema import INDEXES, SCHEMA, open_connection, row_to_dict


class JobStore:
    """Transactional queue writes over a single SQLite file (WAL mode)."""

    def __init__(self, database_path: str) -> None:
        self.path = Path(database_path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open_connection(str(self.path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(SCHEMA)
            for stmt in INDEXES:
                db.execute(stmt)

    def enqueue(
        self,
        kind: str,
        key: str,
        payload: dict[str, Any] | None = None,
        *,
        priority: int = 0,
        max_attempts: int = 3,
        repo: str | None = None,
        now: float | None = None,
    ) -> tuple[str, bool]:
        """Persist a job idempotently. Returns (job_id, created)."""
        now = now if now is not None else time.time()
        with open_connection(str(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                job_id, created = self._upsert(
                    db, kind, key, payload, priority=priority,
                    max_attempts=max_attempts, repo=repo, now=now,
                )
                db.execute("COMMIT")
                return job_id, created
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def _upsert(
        self,
        db,
        kind: str,
        key: str,
        payload: dict[str, Any] | None,
        *,
        priority: int = 0,
        max_attempts: int = 3,
        repo: str | None = None,
        now: float | None = None,
    ) -> tuple[str, bool]:
        """Upsert a job inside an already-open transaction. See :meth:`enqueue`."""
        now = now if now is not None else time.time()
        payload_json = json.dumps(payload or {})
        row = db.execute(
            "SELECT id, status FROM jobs WHERE kind=? AND key=?", (kind, key)
        ).fetchone()
        if row is not None:
            job_id, status = row
            if status in ("pending", "running"):
                db.execute(
                    "UPDATE jobs SET payload=?, reprocess_pending=1, updated_at=? "
                    "WHERE id=?",
                    (payload_json, now, job_id),
                )
            else:
                db.execute(
                    "UPDATE jobs SET payload=?, status='pending', attempts=0, "
                    "reprocess_pending=0, last_error=NULL, next_run_at=?, "
                    "lease_token=NULL, lease_expires_at=NULL, updated_at=? "
                    "WHERE id=?",
                    (payload_json, now, now, job_id),
                )
            return job_id, False
        job_id = uuid.uuid4().hex
        db.execute(
            "INSERT INTO jobs (id, kind, key, payload, priority, status, "
            "attempts, max_attempts, next_run_at, repo, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?, ?)",
            (job_id, kind, key, payload_json, priority, max_attempts, now,
             repo, now, now),
        )
        return job_id, True

    def claim(
        self, now: float | None = None, limit: int = 1, lease_seconds: int = 300
    ) -> list[dict[str, Any]]:
        """Atomically claim the highest-priority due pending jobs."""
        now = now if now is not None else time.time()
        lease = now + lease_seconds
        token = uuid.uuid4().hex
        with open_connection(str(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rows = db.execute(
                    "SELECT * FROM jobs WHERE status='pending' AND next_run_at<=? "
                    "ORDER BY priority DESC, next_run_at ASC LIMIT ?",
                    (now, limit),
                ).fetchall()
                claimed = []
                for row in rows:
                    db.execute(
                        "UPDATE jobs SET status='running', lease_token=?, "
                        "lease_expires_at=?, updated_at=? WHERE id=? AND "
                        "status='pending'",
                        (token, lease, now, row["id"]),
                    )
                    fresh = db.execute(
                        "SELECT * FROM jobs WHERE id=?", (row["id"],)
                    ).fetchone()
                    claimed.append(row_to_dict(fresh))
                db.execute("COMMIT")
                return claimed
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def recover_stale(self, now: float | None = None) -> int:
        """Reset running jobs whose lease expired (or was never set) to pending."""
        now = now if now is not None else time.time()
        with open_connection(str(self.path)) as db:
            cur = db.execute(
                "UPDATE jobs SET status='pending', lease_token=NULL, "
                "lease_expires_at=NULL, updated_at=? WHERE status='running' AND "
                "(lease_expires_at IS NULL OR lease_expires_at < ?)",
                (now, now),
            )
            return cur.rowcount

    def complete(self, job_id: str, status: str, **kwargs: Any) -> dict[str, Any]:
        """Finalize or retry a job (transition logic lives in queue.outcome)."""
        kwargs["now"] = kwargs.get("now", time.time())
        return complete_job(str(self.path), job_id, status, **kwargs)

    def reprocess(self, kind: str, key: str, now: float | None = None) -> bool:
        return reprocess_job(str(self.path), kind, key, now=now)

    def get(self, job_id: str) -> dict[str, Any] | None:
        return get_job(str(self.path), job_id)

    def list_jobs(
        self, *, status: str | None = None, kind: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        return list_jobs(str(self.path), status=status, kind=kind, limit=limit)

    def stats(self) -> dict[str, int]:
        return job_stats(str(self.path))
