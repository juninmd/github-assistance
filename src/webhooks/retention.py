"""Retention for webhook deliveries: bounded batch delete, then VACUUM.

``deliveries`` is an append-only audit log whose payloads are never read back; left
alone it outgrows the volume. Deletes run in small transactions so the WAL and the
lock window stay bounded, and VACUUM then returns the freed pages to the filesystem.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

from src.queue.schema import open_connection
from src.utils.logger import get_logger

BATCH_ROWS = 500
VACUUM_MIN_FREE_RATIO = 0.25
INITIAL_DELAY_SECONDS = 30
_log = get_logger("webhook-retention")


def purge_deliveries(
    path: str, retention_days: int, *, now: float | None = None, batch: int = BATCH_ROWS
) -> dict[str, Any]:
    """Delete deliveries older than ``retention_days`` and VACUUM if enough pages are free."""
    at = now if now is not None else time.time()
    cutoff = datetime.fromtimestamp(at - retention_days * 86400, tz=UTC)
    cutoff_text = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    conn = open_connection(path)
    try:
        # received_at sits after the payload column: without an index every scan walks all overflow pages.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_deliveries_received_at ON deliveries(received_at)"
        )
        deleted = 0
        while True:
            count = conn.execute(
                "DELETE FROM deliveries WHERE rowid IN "
                "(SELECT rowid FROM deliveries WHERE received_at < ? LIMIT ?)",
                (cutoff_text, batch),
            ).rowcount
            deleted += count
            if count < batch:
                break
        pages = conn.execute("PRAGMA page_count").fetchone()[0]
        free = conn.execute("PRAGMA freelist_count").fetchone()[0]
        vacuumed = bool(pages) and free / pages >= VACUUM_MIN_FREE_RATIO
        if vacuumed:
            conn.execute("VACUUM")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    return {"deleted": deleted, "vacuumed": vacuumed, "size_bytes": os.path.getsize(path)}


def run_retention(
    path: str,
    retention_days: int,
    interval_seconds: int,
    stop: threading.Event,
    *,
    initial_delay: float = INITIAL_DELAY_SECONDS,
) -> None:
    """Purge shortly after start, then every interval (pods restart far more often than a day)."""
    wait = initial_delay
    while not stop.wait(wait):
        try:
            _log.info("Deliveries purged", **purge_deliveries(path, retention_days))
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            _log.error("Deliveries purge failed", error=str(exc))
        wait = interval_seconds


def start_retention_thread(
    path: str, retention_days: int, interval_seconds: int
) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()
    thread = threading.Thread(
        target=run_retention,
        args=(path, retention_days, interval_seconds, stop),
        name="webhook-retention",
        daemon=True,
    )
    thread.start()
    return thread, stop
