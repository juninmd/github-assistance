"""Reproducible micro-benchmarks for the durable queue, webhook API and CLI cold start.

Usage:
    uv run python scripts/benchmark.py --out bench.json          # measure this checkout
    uv run python scripts/benchmark.py --compare base.json head.json   # markdown table

Only public, stable entry points are exercised so the same script runs against
older commits (``git worktree add ../base <sha>``) for before/after evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SEED_ROWS = 20_000
STATUSES = ("succeeded", "succeeded", "succeeded", "blocked", "failed", "pending")
COLD_START_MODULES = (
    "src.run_agent",
    "src.agents.pr_assistant.agent",
    "src.insight.cli",
    "src.queue.cli",
    "src.webhooks.server",
)


def _timed(fn: Callable[[], Any], repeat: int) -> dict[str, float]:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return {
        "median_ms": round(statistics.median(samples), 4),
        "p95_ms": round(samples[min(len(samples) - 1, int(len(samples) * 0.95))], 4),
    }


def _seed(store: Any, rows: int) -> None:
    """Bulk-load a realistic history: mixed statuses, 200 repos, 30 days."""
    from src.queue.schema import open_connection

    now = time.time()
    data = [
        (
            f"{i:032x}", "pr", f"acme/repo-{i % 200}#{i}", "{}", i % 3,
            STATUSES[i % len(STATUSES)], 1, 3, now - (rows - i) * 130,
            f"acme/repo-{i % 200}", "merge" if i % 2 else "wait",
            now - (rows - i) * 130, now - (rows - i) * 130 + 40,
        )
        for i in range(rows)
    ]
    with open_connection(str(store.path)) as db:
        db.executemany(
            "INSERT INTO jobs (id, kind, key, payload, priority, status, attempts, "
            "max_attempts, next_run_at, repo, decision, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            data,
        )


def bench_queue(tmp: Path) -> dict[str, dict[str, float]]:
    from src.insight.explain import job_history
    from src.queue.store import JobStore
    from src.queue.worker import QueueWorker, make_observer_handler

    out: dict[str, dict[str, float]] = {}
    store = JobStore(str(tmp / "queue.db"))
    store.initialize()
    _seed(store, SEED_ROWS)
    settings = type("S", (), {"webhook_database_path": str(tmp / "queue.db")})()

    counter = iter(range(10**9))
    out["enqueue (new job)"] = _timed(
        lambda: store.enqueue("pr", f"bench/new#{next(counter)}", {"mode": "observe"}), 300
    )
    out["enqueue (coalesce existing)"] = _timed(
        lambda: store.enqueue("pr", "bench/new#1", {"mode": "observe"}), 300
    )
    out["list_jobs (latest 100)"] = _timed(lambda: store.list_jobs(limit=100), 60)
    out["list_jobs (status=blocked, 100)"] = _timed(
        lambda: store.list_jobs(status="blocked", limit=100), 60
    )
    out["stats (count by status)"] = _timed(store.stats, 60)
    out["job_history (one PR)"] = _timed(
        lambda: job_history(settings, "acme/repo-7#7", 50), 60  # type: ignore[arg-type]
    )

    def claim_complete() -> None:
        for job in store.claim(limit=1):
            store.complete(job["id"], "succeeded", lease_token=job.get("lease_token"))

    out["claim + complete (1 job)"] = _timed(claim_complete, 300)

    drain = JobStore(str(tmp / "drain.db"))
    drain.initialize()
    for i in range(500):
        drain.enqueue("pr", f"bench/drain#{i}", {})
    worker = QueueWorker(drain, make_observer_handler(), limit=10)
    start = time.perf_counter()
    processed = worker.run_until_empty()
    elapsed = (time.perf_counter() - start) * 1000
    out[f"worker drain ({processed} jobs)"] = {"median_ms": round(elapsed, 2), "p95_ms": 0.0}
    return out


def bench_webhook(tmp: Path) -> dict[str, dict[str, float]]:
    from fastapi.testclient import TestClient

    from src.config.settings import Settings
    from src.webhooks.server import create_app

    settings = Settings(
        github_token="x",  # noqa: S106 - benchmark placeholder
        github_webhook_secret="bench-secret",  # noqa: S106 - benchmark placeholder
        admin_api_token="bench-admin",  # noqa: S106 - benchmark placeholder
        webhook_database_path=str(tmp / "webhook.db"),
        worker_enabled=False,
        webhook_purge_enabled=False,
    )
    counter = iter(range(10**9))
    out: dict[str, dict[str, float]] = {}
    with TestClient(create_app(settings)) as client:

        def post() -> None:
            n = next(counter)
            body = json.dumps(
                {
                    "action": "synchronize",
                    "number": n,
                    "pull_request": {"number": n},
                    "repository": {"full_name": f"acme/repo-{n % 20}"},
                }
            ).encode()
            sig = "sha256=" + hmac.new(b"bench-secret", body, hashlib.sha256).hexdigest()
            client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Delivery": f"d-{n}",
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": sig,
                },
            ).raise_for_status()

        out["POST /webhooks/github"] = _timed(post, 300)
        auth = {"Authorization": "Bearer bench-admin"}
        out["GET /api/jobs?limit=100"] = _timed(
            lambda: client.get("/api/jobs?limit=100", headers=auth).raise_for_status(), 60
        )
    return out


def bench_cold_start() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for module in COLD_START_MODULES:
        out[f"cold import {module}"] = _timed(
            lambda m=module: subprocess.run(  # noqa: S603 - fixed argv
                [sys.executable, "-c", f"import {m}"], check=True, cwd=ROOT
            ),
            7,
        )
    return out


def run(out_path: str | None) -> None:
    results: dict[str, dict[str, float]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        results.update(bench_queue(Path(tmp)))
        results.update(bench_webhook(Path(tmp)))
    results.update(bench_cold_start())
    payload = {"seed_rows": SEED_ROWS, "python": sys.version.split()[0], "results": results}
    text = json.dumps(payload, indent=2)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
    print(text)


def compare(base_path: str, head_path: str) -> None:
    base = json.loads(Path(base_path).read_text(encoding="utf-8"))["results"]
    head = json.loads(Path(head_path).read_text(encoding="utf-8"))["results"]
    print("| Scenario | Before (ms) | After (ms) | Speedup |")
    print("|---|---:|---:|---:|")
    for name, after in head.items():
        before = base.get(name)
        if not before:
            print(f"| {name} | n/a | {after['median_ms']:.3f} | new |")
            continue
        speedup = before["median_ms"] / after["median_ms"] if after["median_ms"] else 0.0
        print(
            f"| {name} | {before['median_ms']:.3f} | {after['median_ms']:.3f} | {speedup:.2f}x |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", help="write the JSON results to this path")
    parser.add_argument("--compare", nargs=2, metavar=("BASE", "HEAD"))
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare)
    else:
        run(args.out)


if __name__ == "__main__":
    main()
