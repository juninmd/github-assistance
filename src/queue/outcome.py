"""Job completion/retry transition logic for the durable queue."""

from __future__ import annotations

import time
from typing import Any

from src.queue.schema import open_connection, row_to_dict

FINAL_STATUSES = ("succeeded", "blocked")
RETRYABLE_STATUSES = ("failed",)


def complete_job(
    path: str,
    job_id: str,
    status: str,
    *,
    error: str | None = None,
    decision: str | None = None,
    next_action: str | None = None,
    sha: str | None = None,
    task_id: str | None = None,
    now: float | None = None,
    backoff_seconds: int = 60,
    lease_token: str | None = None,
) -> dict[str, Any]:
    """Finalize (succeeded/blocked) or retry (failed, attempts left) a job.

    With ``lease_token``, the write is dropped (returns ``{}``) when the lease
    no longer belongs to the caller.
    """
    now = now if now is not None else time.time()
    with open_connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute(
                "SELECT attempts, max_attempts, reprocess_pending, lease_token FROM jobs "
                "WHERE id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                db.execute("ROLLBACK")
                return {}
            attempts, max_attempts, reprocess_pending, current_token = row
            if lease_token is not None and current_token != lease_token:
                # Lease expired and another worker re-claimed the job; its outcome wins.
                db.execute("ROLLBACK")
                return {}
            next_status, immediate = _next(status, attempts, max_attempts, reprocess_pending)
            if next_status == "pending":
                delay = 0 if immediate else backoff_seconds * (attempts + 1)
                db.execute(
                    "UPDATE jobs SET status='pending', attempts=?, "
                    "reprocess_pending=0, next_run_at=?, lease_token=NULL, "
                    "lease_expires_at=NULL, last_error=?, decision=?, "
                    "next_action=?, sha=?, task_id=?, updated_at=? WHERE id=?",
                    (attempts + 1, now + delay, error, decision, next_action,
                     sha, task_id, now, job_id),
                )
            else:
                db.execute(
                    "UPDATE jobs SET status=?, attempts=?, lease_token=NULL, "
                    "lease_expires_at=NULL, last_error=?, decision=?, "
                    "next_action=?, sha=?, task_id=?, updated_at=? WHERE id=?",
                    (next_status, attempts + 1, error, decision, next_action,
                     sha, task_id, now, job_id),
                )
            db.execute("COMMIT")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return row_to_dict(row) if row else {}
        except BaseException:
            db.execute("ROLLBACK")
            raise


def reprocess_job(path: str, kind: str, key: str, now: float | None = None) -> bool:
    """Reset a finished job to pending (idempotent CLI reprocessing)."""
    now = now if now is not None else time.time()
    with open_connection(path) as db:
        cur = db.execute(
            "UPDATE jobs SET status='pending', attempts=0, reprocess_pending=0, "
            "next_run_at=?, lease_token=NULL, updated_at=? WHERE kind=? AND key=?",
            (now, now, kind, key),
        )
        return cur.rowcount > 0


def _next(
    status: str, attempts: int, max_attempts: int, reprocess_pending: int
) -> tuple[str, bool]:
    if reprocess_pending and status in FINAL_STATUSES:
        # A new event landed while this round ran: re-evaluate immediately.
        return "pending", True
    if status in RETRYABLE_STATUSES:
        return ("pending", False) if attempts + 1 < max_attempts else ("blocked", False)
    return status, False
