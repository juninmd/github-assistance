"""Durable job queue persisted in SQLite.

Jobs survive restarts, are claimed with expiring leases, retried with bounded
attempts, and deduplicated per (kind, key) so webhook/CLI/batch inputs never
lose events or duplicate effects.
"""

from src.queue.store import JobStore
from src.queue.worker import QueueWorker

__all__ = ["JobStore", "QueueWorker"]
