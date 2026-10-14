"""SQLite schema, connection and row mapping for the durable job queue."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    payload TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_run_at REAL NOT NULL,
    lease_token TEXT,
    lease_expires_at REAL,
    reprocess_pending INTEGER NOT NULL DEFAULT 0,
    task_id TEXT,
    repo TEXT,
    sha TEXT,
    decision TEXT,
    next_action TEXT,
    last_error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(kind, key)
)
"""
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, next_run_at)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_kind_key ON jobs(kind, key)",
)
COLUMNS = (
    "id", "kind", "key", "payload", "priority", "status", "attempts",
    "max_attempts", "next_run_at", "lease_token", "lease_expires_at",
    "reprocess_pending", "task_id", "repo", "sha", "decision",
    "next_action", "last_error", "created_at", "updated_at",
)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = {col: row[col] for col in COLUMNS}
    data["reprocess_pending"] = bool(data["reprocess_pending"])
    try:
        data["payload"] = json.loads(data["payload"])
    except (TypeError, json.JSONDecodeError):
        data["payload"] = {}
    return data


def open_connection(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn
