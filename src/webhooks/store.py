"""Durable webhook delivery state + atomic webhook-to-job persistence."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from src.queue.store import JobStore


class DeliveryStore:
    """Persists webhook deliveries and enqueues PR jobs atomically."""

    def __init__(self, database_path: str) -> None:
        self.path = Path(database_path)
        self.jobs = JobStore(database_path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
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
        self.jobs.initialize()

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
        conn = self._connect(isolation=None)
        created = False
        job_ids: list[str] = []
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO deliveries
                    (delivery_id, event, action, repository, payload)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (delivery_id, event, action, repository, json.dumps(payload)),
                )
                created = cur.rowcount > 0
                for pr_ref in pr_refs if created else []:
                    repo = pr_ref.split("#", 1)[0]
                    job_id, _ = self.jobs._upsert(
                        conn,
                        "pr",
                        pr_ref,
                        {
                            "mode": mode,
                            "event": event,
                            "action": action,
                            "delivery_id": delivery_id,
                        },
                        priority=priority,
                        repo=repo,
                        now=now,
                    )
                    job_ids.append(job_id)
                conn.execute("COMMIT")
                return created, job_ids
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    def record(self, delivery_id: str, event: str, payload: dict[str, Any]) -> bool:
        action = payload.get("action")
        repository = payload.get("repository", {}).get("full_name")
        try:
            with self._connect() as db:
                db.execute(
                    """
                    INSERT INTO deliveries
                    (delivery_id, event, action, repository, payload)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (delivery_id, event, action, repository, json.dumps(payload)),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def ready(self) -> bool:
        try:
            with self._connect() as db:
                db.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def _connect(self, isolation: str | None = None) -> sqlite3.Connection:
        kwargs: dict[str, Any] = {"timeout": 5}
        if isolation is not None:
            kwargs["isolation_level"] = isolation
        conn = sqlite3.connect(self.path, **kwargs)
        conn.row_factory = sqlite3.Row
        return conn
