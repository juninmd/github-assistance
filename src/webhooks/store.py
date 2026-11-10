"""Durable webhook delivery state + atomic webhook-to-job persistence."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.queue.schema import connection
from src.queue.store import JobStore


class DeliveryStore:
    """Persists webhook deliveries and enqueues PR jobs atomically."""

    def __init__(self, database_path: str) -> None:
        self.path = Path(database_path)
        self.jobs = JobStore(database_path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.jobs.initialize()
        self._db().execute(
            """
                CREATE TABLE IF NOT EXISTS deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    event TEXT NOT NULL,
                    action TEXT,
                    repository TEXT,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'observed',
                    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
        )
        # received_at sits after the payload column: unindexed scans walk every overflow page.
        self._db().execute(
            "CREATE INDEX IF NOT EXISTS idx_deliveries_received_at ON deliveries(received_at)"
        )

    def record_and_enqueue(
        self,
        delivery_id: str,
        event: str,
        payload: dict[str, Any],
        pr_refs: list[str],
        *,
        mode: str,
        priority: int = 0,
        now: float | None = None,
    ) -> tuple[bool, list[str]]:
        """Persist the delivery and the PR job in a single transaction.

        A crash between the webhook and the worker cannot lose the job, and a
        duplicated delivery never creates a second job or reopens a finished one.
        """
        now = now if now is not None else time.time()
        action = payload.get("action")
        repository = payload.get("repository", {}).get("full_name")
        conn = self._db()
        job_ids: list[str] = []
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO deliveries (delivery_id, event, action, repository, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (delivery_id, event, action, repository, json.dumps(payload)),
            )
            created = cur.rowcount > 0
            job_payload = {
                "mode": mode, "event": event, "action": action, "delivery_id": delivery_id,
            }
            for pr_ref in pr_refs if created else []:
                job_id, _ = self.jobs._upsert(
                    conn, "pr", pr_ref, job_payload,
                    priority=priority, repo=pr_ref.split("#", 1)[0], now=now,
                )
                job_ids.append(job_id)
            conn.execute("COMMIT")
            return created, job_ids
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def record(self, delivery_id: str, event: str, payload: dict[str, Any]) -> bool:
        action = payload.get("action")
        repository = payload.get("repository", {}).get("full_name")
        try:
            self._db().execute(
                "INSERT INTO deliveries (delivery_id, event, action, repository, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (delivery_id, event, action, repository, json.dumps(payload)),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def event_counts(self, hours: int, now: float | None = None) -> list[dict[str, Any]]:
        """Webhook deliveries per event type over the last ``hours`` (retention-bounded)."""
        at = now if now is not None else time.time()
        cutoff = datetime.fromtimestamp(at - hours * 3600, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        rows = self._db().execute(
            "SELECT event AS label, COUNT(*) AS n FROM deliveries WHERE received_at >= ? "
            "GROUP BY event ORDER BY n DESC, event",
            (cutoff,),
        )
        return [{"label": row["label"], "value": row["n"]} for row in rows]

    def ready(self) -> bool:
        try:
            self._db().execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def _db(self) -> sqlite3.Connection:
        """Thread-cached connection shared with the job queue (same file, same lock)."""
        return connection(str(self.path))
