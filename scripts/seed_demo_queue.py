"""Seed a throwaway queue database with realistic demo data for the dashboard.

Usage:
    uv run python scripts/seed_demo_queue.py --db /tmp/demo/webhooks.db
    ADMIN_API_TOKEN=demo WEBHOOK_DATABASE_PATH=/tmp/demo/webhooks.db WORKER_ENABLED=false \
        GITHUB_TOKEN=x uv run webhook-server      # then open http://localhost:8080/dashboard/

Deterministic (fixed seed) so screenshots are reproducible. Refuses to touch a
database that already holds jobs.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.queue.schema import connection  # noqa: E402
from src.webhooks.store import DeliveryStore  # noqa: E402

REPOS = (
    "octo-demo/storefront", "octo-demo/billing-api", "octo-demo/design-system",
    "octo-demo/mobile-app", "octo-demo/infra-k8s", "octo-demo/data-pipeline",
    "octo-demo/docs-site", "octo-demo/auth-service", "octo-demo/notifier",
    "octo-demo/search-indexer",
)
EVENTS = (
    ("pull_request", 34), ("check_suite", 27), ("workflow_run", 22),
    ("pull_request_review", 11), ("issue_comment", 6),
)
BLOCK_REASONS = (
    "ci_failed: 2 checks failing on head SHA",
    "review_rejected: evaluator returned REJECT",
    "merge_conflicts: branch cannot be updated against base",
)
RETRY_ERRORS = (
    "GitHub API 502 Bad Gateway while fetching check runs",
    "pipeline evidence still pending after update_pr_branch",
)
HOUR = 3600


def _age_seconds(rng: random.Random) -> float:
    """Skew towards the last day, with a working-hours bump."""
    age = rng.expovariate(1 / (20 * HOUR))
    hour_of_day = datetime.fromtimestamp(time.time() - age, tz=UTC).hour
    busy = 0.55 + 0.45 * math.sin((hour_of_day - 7) / 24 * 2 * math.pi)
    return age if rng.random() < busy else age + rng.uniform(2, 9) * HOUR


def _job(rng: random.Random, index: int, now: float) -> tuple:
    repo = rng.choices(REPOS, weights=range(len(REPOS), 0, -1))[0]
    updated = now - min(_age_seconds(rng), 7 * 24 * HOUR - 60)
    created = updated - rng.uniform(40, 900)
    roll = rng.random()
    status, attempts, decision, action, error, next_run = "succeeded", 1, "merge", "none", None, updated
    if roll < 0.14:
        status, decision, action, error = "blocked", "blocked", "fix", rng.choice(BLOCK_REASONS)
        attempts = rng.choice((1, 3, 3))
    elif roll < 0.19:
        status, attempts, decision, action = "pending", rng.choice((1, 2)), "wait", "retry"
        error, next_run = rng.choice(RETRY_ERRORS), now + rng.uniform(-200, 240)
    elif roll < 0.215:
        status, attempts, decision, action = "pending", 0, None, None
        updated = now - rng.uniform(20, 1500)
        created, next_run = updated, updated
    elif roll < 0.42:
        decision, action = "observed", "observe"
    payload = {"mode": "autonomous", "event": rng.choice(EVENTS)[0], "action": "synchronize"}
    return (
        f"{index:032x}", "pr", f"{repo}#{100 + index}", json.dumps(payload), rng.choice((0, 0, 0, 5)),
        status, attempts, 3, next_run, repo, f"{rng.getrandbits(160):040x}", decision, action,
        error, created, updated,
    )


def seed(database_path: str, *, jobs: int = 460, now: float | None = None) -> dict[str, int]:
    now = now if now is not None else time.time()
    rng = random.Random(7)  # noqa: S311 - demo data, not security sensitive
    store = DeliveryStore(database_path)
    store.initialize()
    db = connection(database_path)
    if db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]:
        raise SystemExit(f"{database_path} already has jobs; refusing to seed over real data")
    db.execute("BEGIN IMMEDIATE")
    db.executemany(
        "INSERT INTO jobs (id, kind, key, payload, priority, status, attempts, max_attempts, "
        "next_run_at, repo, sha, decision, next_action, last_error, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [_job(rng, index, now) for index in range(jobs)],
    )
    db.execute(
        "UPDATE jobs SET status='running', lease_token='demo', lease_expires_at=?, updated_at=? "
        "WHERE id IN (SELECT id FROM jobs WHERE status='pending' ORDER BY attempts LIMIT 2)",
        (now + 240, now - 35),
    )
    deliveries = []
    for index in range(jobs * 3):
        event = rng.choices([name for name, _ in EVENTS], weights=[w for _, w in EVENTS])[0]
        received = datetime.fromtimestamp(now - rng.uniform(0, 3 * 24 * HOUR), tz=UTC)
        deliveries.append((f"demo-{index}", event, "synchronize", rng.choice(REPOS), "{}",
                           received.strftime("%Y-%m-%d %H:%M:%S")))
    db.executemany(
        "INSERT INTO deliveries (delivery_id, event, action, repository, payload, received_at) "
        "VALUES (?,?,?,?,?,?)",
        deliveries,
    )
    db.execute("COMMIT")
    return {"jobs": jobs, "deliveries": len(deliveries)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", required=True, help="path of the demo SQLite database to create")
    parser.add_argument("--jobs", type=int, default=460)
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(seed(args.db, jobs=args.jobs)))


if __name__ == "__main__":
    main()
