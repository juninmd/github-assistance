"""CLI: `queue-worker` — durable worker, reprocess, list and stats.

The worker runs as a one-shot (Kubernetes Job / `--once`) or as a daemon loop
(webhook server). `--observe` uses the no-external-effect handler.
"""

from __future__ import annotations

import argparse
import json

from src.config.settings import Settings
from src.queue.store import JobStore
from src.queue.worker import QueueWorker, make_observer_handler
from src.webhooks.dispatcher import make_pr_handler


def _store(settings: Settings) -> JobStore:
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    return store


def cmd_worker(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    store = _store(settings)
    handler = make_observer_handler() if args.observe else make_pr_handler(settings)
    worker = QueueWorker(
        store,
        handler,
        lease_seconds=settings.queue_lease_seconds,
        backoff_seconds=settings.queue_backoff_seconds,
        limit=settings.max_concurrent_workers,
    )
    if args.once:
        processed = worker.run_until_empty()
        print(f"processed={processed}")
        return
    print(f"worker started (poll={settings.queue_poll_interval_seconds}s); Ctrl+C to stop")
    try:
        worker.run(poll_interval=settings.queue_poll_interval_seconds)
    except KeyboardInterrupt:
        print("\nworker stopped")


def cmd_reprocess(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    store = _store(settings)
    ok = store.reprocess("pr", args.pr)
    print(f"reprocess {'ok' if ok else 'no-op'} for {args.pr}")


def cmd_list(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    store = _store(settings)
    jobs = store.list_jobs(status=args.status, limit=args.limit)
    if args.json:
        print(json.dumps({"jobs": jobs}, indent=2, default=str))
        return
    for job in jobs:
        print(
            f"{job['key']:<40} {job['status']:<9} attempts={job['attempts']} "
            f"decision={job['decision'] or '-'}"
        )


def cmd_stats(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    store = _store(settings)
    stats = store.stats()
    if args.json:
        print(json.dumps(stats, indent=2))
        return
    for status, count in sorted(stats.items()):
        print(f"{status:<10} {count}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="queue-worker", description="Durable job queue worker")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("worker", help="process queued jobs")
    run.add_argument("--once", action="store_true", help="drain the queue once and exit")
    run.add_argument("--observe", action="store_true", help="observe-only handler (no writes)")

    reprocess = sub.add_parser("reprocess", help="idempotently re-queue a finished PR job")
    reprocess.add_argument("--pr", required=True, help="owner/repo#number")

    listing = sub.add_parser("list", help="list queued jobs")
    listing.add_argument("--status", help="filter by status")
    listing.add_argument("--limit", type=int, default=100)
    listing.add_argument("--json", action="store_true")

    stats = sub.add_parser("stats", help="job counts by status")
    stats.add_argument("--json", action="store_true")

    args = parser.parse_args()
    {"worker": cmd_worker, "reprocess": cmd_reprocess, "list": cmd_list, "stats": cmd_stats}[
        args.command
    ](args)


if __name__ == "__main__":
    main()
