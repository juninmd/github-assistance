"""Read-only queries over the durable job queue."""

from __future__ import annotations

from typing import Any

from src.queue.schema import open_connection, row_to_dict


def get_job(database_path: str, job_id: str) -> dict[str, Any] | None:
    with open_connection(database_path) as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return row_to_dict(row) if row else None


def list_jobs(
    database_path: str,
    *,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if status and kind:
        sql = "SELECT * FROM jobs WHERE status=? AND kind=? ORDER BY created_at DESC LIMIT ?"
        params: list[Any] = [status, kind, limit]
    elif status:
        sql = "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?"
        params = [status, limit]
    elif kind:
        sql = "SELECT * FROM jobs WHERE kind=? ORDER BY created_at DESC LIMIT ?"
        params = [kind, limit]
    else:
        sql = "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?"
        params = [limit]
    with open_connection(database_path) as db:
        rows = db.execute(sql, params).fetchall()
        return [row_to_dict(r) for r in rows]


def job_stats(database_path: str) -> dict[str, int]:
    with open_connection(database_path) as db:
        rows = db.execute(
            "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
        ).fetchall()
        return {row["status"]: row["n"] for row in rows}
