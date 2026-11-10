"""Read-only queries over the durable job queue."""

from __future__ import annotations

from typing import Any

from src.queue.schema import connection, row_to_dict

# Column filters accepted by ``list_jobs`` (equality match, index-backed).
_EQUALITY_FILTERS = ("status", "kind", "repo", "key")


def get_job(database_path: str, job_id: str) -> dict[str, Any] | None:
    row = connection(database_path).execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return row_to_dict(row) if row else None


def _where(filters: dict[str, Any], search: str | None) -> tuple[str, list[Any]]:
    clauses = [f"{column}=?" for column in _EQUALITY_FILTERS if filters.get(column)]
    params: list[Any] = [filters[column] for column in _EQUALITY_FILTERS if filters.get(column)]
    if search:
        clauses.append("instr(lower(key), lower(?)) > 0")
        params.append(search)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def list_jobs(
    database_path: str,
    *,
    status: str | None = None,
    kind: str | None = None,
    repo: str | None = None,
    key: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Newest-first jobs, filtered in SQL so ``limit`` applies after the filters."""
    where, params = _where({"status": status, "kind": kind, "repo": repo, "key": key}, search)
    rows = connection(database_path).execute(
        f"SELECT * FROM jobs{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",  # noqa: S608
        [*params, limit, offset],
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def count_jobs(
    database_path: str,
    *,
    status: str | None = None,
    kind: str | None = None,
    repo: str | None = None,
    search: str | None = None,
) -> int:
    where, params = _where({"status": status, "kind": kind, "repo": repo}, search)
    row = connection(database_path).execute(
        f"SELECT COUNT(*) FROM jobs{where}", params  # noqa: S608
    ).fetchone()
    return int(row[0])


def job_stats(database_path: str) -> dict[str, int]:
    rows = connection(database_path).execute(
        "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
    ).fetchall()
    return {row["status"]: row["n"] for row in rows}
