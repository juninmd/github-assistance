"""Durable webhook delivery state."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class DeliveryStore:
    def __init__(self, database_path: str) -> None:
        self.path = Path(database_path)

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

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)
