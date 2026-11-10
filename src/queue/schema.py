"""SQLite schema, connection and row mapping for the durable job queue."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
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
    # Claim path: ordered scan of due pending jobs, no temp sort.
    "CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs(status, priority DESC, next_run_at)",
    # Listing paths (API, CLI, dashboard): newest first, optionally by status.
    "CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at DESC)",
    # Dashboard throughput: finished jobs by completion time.
    "CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at)",
)
# Superseded: idx_jobs_status by idx_jobs_claim; idx_jobs_kind_key duplicated UNIQUE(kind, key).
DROPPED_INDEXES = ("idx_jobs_status", "idx_jobs_kind_key")
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
    """Open a fresh autocommit connection; the caller owns and closes it."""
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


_MAX_CACHED_CONNECTIONS = 8
_local = threading.local()


def connection(path: str) -> sqlite3.Connection:
    """Return this thread's cached connection to ``path`` (never close it).

    Opening a connection and re-parsing the schema dominated every queue
    operation. The cache is per thread (SQLite connections are not shared across
    threads) and is invalidated when the file is replaced (inode change).
    """
    cache: dict[str, tuple[int, sqlite3.Connection]] = _local.__dict__.setdefault("cache", {})
    inode = _inode(path)
    cached = cache.get(path)
    if cached is not None:
        if inode is not None and cached[0] == inode:
            return cached[1]
        cache.pop(path)[1].close()
    while len(cache) >= _MAX_CACHED_CONNECTIONS:
        cache.pop(next(iter(cache)))[1].close()
    conn = open_connection(path)
    cache[path] = (_inode(path) or -1, conn)
    return conn


def _inode(path: str) -> int | None:
    try:
        return os.stat(path).st_ino
    except OSError:
        return None
