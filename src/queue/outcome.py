"""Job completion/retry transition logic for the durable queue."""

from __future__ import annotations

import time
from typing import Any

from src.queue.schema import connection, row_to_dict

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
    db = connection(path)
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute(
            "SELECT attempts, max_attempts, reprocess_pending, lease_token FROM jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if row is None or (lease_token is not None and row["lease_token"] != lease_token):
            # Unknown job, or the lease expired and another worker re-claimed it: its outcome wins.
            db.execute("ROLLBACK")
            return {}
        attempts = row["attempts"]
        next_status, immediate = _next(
            status, attempts, row["max_attempts"], row["reprocess_pending"]
        )
        retrying = next_status == "pending"
        delay = 0 if immediate else backoff_seconds * (attempts + 1)
        updated = db.execute(
            "UPDATE jobs SET status=?, attempts=?, lease_token=NULL, lease_expires_at=NULL, "
            "reprocess_pending=CASE WHEN ? THEN 0 ELSE reprocess_pending END, "
            "next_run_at=CASE WHEN ? THEN ? ELSE next_run_at END, "
            "last_error=?, decision=?, next_action=?, sha=?, task_id=?, updated_at=? "
            "WHERE id=? RETURNING *",
            (next_status, attempts + 1, retrying, retrying, now + delay, error, decision,
             next_action, sha, task_id, now, job_id),
        ).fetchall()
        db.execute("COMMIT")
        return row_to_dict(updated[0]) if updated else {}
    except BaseException:
        db.execute("ROLLBACK")
        raise


def reprocess_job(path: str, kind: str, key: str, now: float | None = None) -> bool:
    """Reset a finished job to pending (idempotent CLI reprocessing)."""
    now = now if now is not None else time.time()
    cur = connection(path).execute(
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
