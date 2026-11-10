"""Aggregated queue metrics for the dashboard (`GET /api/overview`).

Every figure is computed in SQL over a bounded time window so the endpoint stays
cheap enough to poll. The queue keeps one row per ``(kind, key)``, so "outcomes"
describe each job's *latest* round, bucketed by when it last changed.
"""

from __future__ import annotations

import time
from typing import Any

from src.queue.schema import connection

HOUR = 3600
MAX_WINDOW_HOURS = 24 * 7
TOP_N = 8
# A job that failed and is waiting for its next attempt is "retrying".
_OUTCOME = (
    "CASE WHEN status IN ('succeeded', 'blocked') THEN status "
    "WHEN status = 'pending' AND attempts > 0 THEN 'retrying' END"
)


def bucket_seconds(hours: int) -> int:
    """Hourly buckets up to two days, six-hour buckets beyond."""
    return HOUR if hours <= 48 else 6 * HOUR


def queue_overview(database_path: str, *, hours: int = 24, now: float | None = None) -> dict[str, Any]:
    now = now if now is not None else time.time()
    hours = max(1, min(hours, MAX_WINDOW_HOURS))
    step = bucket_seconds(hours)
    buckets = hours * HOUR // step
    start = (int(now) // step + 1) * step - buckets * step
    db = connection(database_path)

    totals = {
        row["status"]: row["n"]
        for row in db.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")
    }
    backlog = db.execute(
        "SELECT COUNT(*) FILTER (WHERE next_run_at <= :now) AS due, "
        "COUNT(*) FILTER (WHERE next_run_at > :now) AS scheduled, "
        "COUNT(*) FILTER (WHERE attempts > 0) AS retrying, "
        "MIN(next_run_at) AS oldest FROM jobs WHERE status = 'pending'",
        {"now": now},
    ).fetchone()
    series = [
        {"start": start + index * step, "succeeded": 0, "blocked": 0, "retrying": 0}
        for index in range(buckets)
    ]
    for row in db.execute(
        f"SELECT CAST((updated_at - ?) / ? AS INTEGER) AS bucket, {_OUTCOME} AS outcome, "  # noqa: S608
        "COUNT(*) AS n FROM jobs WHERE updated_at >= ? GROUP BY bucket, outcome",
        (start, step, start),
    ):
        if row["outcome"] and 0 <= row["bucket"] < buckets:
            series[row["bucket"]][row["outcome"]] = row["n"]
    succeeded = sum(point["succeeded"] for point in series)
    blocked = sum(point["blocked"] for point in series)
    finished = succeeded + blocked
    oldest = backlog["oldest"]
    return {
        "generated_at": now,
        "window_hours": hours,
        "bucket_seconds": step,
        "totals": totals,
        "backlog": {
            "due": backlog["due"],
            "scheduled": backlog["scheduled"],
            "retrying": backlog["retrying"],
            "running": totals.get("running", 0),
            "oldest_due_age_seconds": max(0.0, now - oldest) if oldest and oldest <= now else 0.0,
        },
        "window": {
            "succeeded": succeeded,
            "blocked": blocked,
            "retrying": sum(point["retrying"] for point in series),
            "success_rate": round(succeeded / finished, 4) if finished else None,
        },
        "throughput": series,
        "decisions": _ranked(db, "COALESCE(decision, '')", start),
        "repositories": _repositories(db, start),
    }


def _ranked(db: Any, expression: str, start: float) -> list[dict[str, Any]]:
    rows = db.execute(
        f"SELECT {expression} AS label, COUNT(*) AS n FROM jobs WHERE updated_at >= ? "  # noqa: S608
        "GROUP BY label ORDER BY n DESC, label LIMIT ?",
        (start, TOP_N),
    )
    return [{"label": row["label"], "value": row["n"]} for row in rows]


def _repositories(db: Any, start: float) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT COALESCE(repo, '') AS label, COUNT(*) AS n, "
        "COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded, "
        "COUNT(*) FILTER (WHERE status = 'blocked') AS blocked, "
        "COUNT(*) FILTER (WHERE status IN ('pending', 'running')) AS open "
        "FROM jobs WHERE updated_at >= ? GROUP BY label ORDER BY n DESC, label LIMIT ?",
        (start, TOP_N),
    )
    return [
        {
            "label": row["label"],
            "value": row["n"],
            "succeeded": row["succeeded"],
            "blocked": row["blocked"],
            "open": row["open"],
        }
        for row in rows
    ]
