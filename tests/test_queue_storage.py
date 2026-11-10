"""Queue storage internals: cached connections, indexes, SQL filters, overview."""

import os
import sqlite3
import threading

from src.insight.explain import job_history
from src.queue.overview import bucket_seconds, queue_overview
from src.queue.schema import _MAX_CACHED_CONNECTIONS, connection
from src.queue.store import JobStore
from src.webhooks.store import DeliveryStore

NOW = 1_800_000_000.0


def _store(tmp_path, name="queue.db") -> JobStore:
    store = JobStore(str(tmp_path / name))
    store.initialize()
    return store


def test_connection_is_cached_per_thread_and_per_file(tmp_path):
    path = str(tmp_path / "a.db")
    first = connection(path)
    assert connection(path) is first
    other: list[sqlite3.Connection] = []
    thread = threading.Thread(target=lambda: other.append(connection(path)))
    thread.start()
    thread.join()
    assert other[0] is not first


def test_connection_is_reopened_when_the_file_is_replaced(tmp_path):
    path = tmp_path / "a.db"
    first = connection(str(path))
    first.execute("CREATE TABLE t (x)")
    os.replace(path, tmp_path / "old.db")
    fresh = connection(str(path))
    assert fresh is not first
    assert fresh.execute("SELECT name FROM sqlite_master").fetchall() == []


def test_connection_cache_is_bounded(tmp_path):
    first = connection(str(tmp_path / "0.db"))
    for index in range(1, _MAX_CACHED_CONNECTIONS + 1):
        connection(str(tmp_path / f"{index}.db"))
    assert connection(str(tmp_path / "0.db")) is not first


def test_initialize_migrates_superseded_indexes(tmp_path):
    store = _store(tmp_path)
    db = connection(str(store.path))
    db.execute("CREATE INDEX idx_jobs_status ON jobs(status, next_run_at)")
    db.execute("CREATE INDEX idx_jobs_kind_key ON jobs(kind, key)")
    store.initialize()
    names = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_jobs_claim", "idx_jobs_created", "idx_jobs_status_created"} <= names
    assert not {"idx_jobs_status", "idx_jobs_kind_key"} & names


def test_claim_returns_highest_priority_first_in_one_statement(tmp_path):
    store = _store(tmp_path)
    store.enqueue("pr", "o/r#1", priority=0, now=NOW)
    store.enqueue("pr", "o/r#2", priority=9, now=NOW + 1)
    store.enqueue("pr", "o/r#3", priority=9, now=NOW)
    store.enqueue("pr", "o/r#4", priority=0, now=NOW + 500)  # not due yet
    claimed = store.claim(now=NOW + 10, limit=5, lease_seconds=60)
    assert [job["key"] for job in claimed] == ["o/r#3", "o/r#2", "o/r#1"]
    assert {job["status"] for job in claimed} == {"running"}
    assert len({job["lease_token"] for job in claimed}) == 1
    assert claimed[0]["lease_expires_at"] == NOW + 70
    assert store.claim(now=NOW + 10) == []


def test_list_jobs_filters_in_sql_and_paginates(tmp_path):
    store = _store(tmp_path)
    for index in range(6):
        store.enqueue("pr", f"acme/api#{index}", repo="acme/api", now=NOW + index)
    store.enqueue("pr", "acme/web#1", repo="acme/web", now=NOW + 50)
    job = store.claim(now=NOW + 100, limit=1)[0]
    store.complete(job["id"], "succeeded", now=NOW + 101)

    assert [j["key"] for j in store.list_jobs(limit=2)] == ["acme/web#1", "acme/api#5"]
    assert [j["key"] for j in store.list_jobs(limit=2, offset=2)] == ["acme/api#4", "acme/api#3"]
    assert store.count() == 7 and store.count(repo="acme/web") == 1
    assert store.count(status="succeeded") == 1 and store.count(search="API#") == 6
    assert [j["key"] for j in store.list_jobs(search="web")] == ["acme/web#1"]
    assert store.list_jobs(key="acme/api#0")[0]["repo"] == "acme/api"
    assert store.list_jobs(status="blocked") == []


def test_job_history_finds_a_pr_older_than_the_page(tmp_path):
    store = _store(tmp_path)
    store.enqueue("pr", "acme/api#old", now=NOW)
    for index in range(60):
        store.enqueue("pr", f"acme/api#{index}", now=NOW + 1 + index)
    settings = type("S", (), {"webhook_database_path": str(store.path)})()
    history = job_history(settings, "acme/api#old", limit=50)
    assert [job["key"] for job in history] == ["acme/api#old"]
    assert len(job_history(settings, limit=50)) == 50


def test_overview_aggregates_backlog_window_and_rankings(tmp_path):
    store = _store(tmp_path)
    now = NOW + 1800  # half-way through an hourly bucket
    outcomes = [("succeeded", "merge"), ("succeeded", "merge"), ("blocked", "blocked"), ("failed", "wait")]
    for index, (status, decision) in enumerate(outcomes):
        store.enqueue("pr", f"acme/api#{index}", repo="acme/api", now=now - 4000)
        job = store.claim(now=now - 3900, limit=1)[0]
        store.complete(
            job["id"], status, decision=decision, error="boom", now=now - 3700, backoff_seconds=9000
        )
    store.enqueue("pr", "acme/web#1", repo="acme/web", now=now - 600)
    store.enqueue("pr", "acme/web#2", repo="acme/web", now=now - 30)
    store.claim(now=now - 20, limit=1)

    data = queue_overview(str(store.path), hours=24, now=now)
    assert data["totals"] == {"blocked": 1, "pending": 2, "running": 1, "succeeded": 2}
    assert data["backlog"]["due"] == 1 and data["backlog"]["scheduled"] == 1
    assert data["backlog"]["retrying"] == 1 and data["backlog"]["running"] == 1
    assert data["backlog"]["oldest_due_age_seconds"] == 30
    assert data["window"] == {"succeeded": 2, "blocked": 1, "retrying": 1, "success_rate": 0.6667}
    assert len(data["throughput"]) == 24 and data["bucket_seconds"] == 3600
    assert data["throughput"][-1]["start"] <= now < data["throughput"][-1]["start"] + 3600
    assert sum(p["succeeded"] for p in data["throughput"]) == 2
    assert {"label": "merge", "value": 2} in data["decisions"]
    assert data["repositories"][0] == {
        "label": "acme/api", "value": 4, "succeeded": 2, "blocked": 1, "open": 1,
    }


def test_overview_handles_an_empty_queue_and_long_windows(tmp_path):
    store = _store(tmp_path)
    data = queue_overview(str(store.path), hours=10_000, now=NOW)
    assert data["window_hours"] == 168 and len(data["throughput"]) == 28
    assert data["window"]["success_rate"] is None and data["backlog"]["oldest_due_age_seconds"] == 0
    assert bucket_seconds(48) == 3600 and bucket_seconds(49) == 6 * 3600


def test_delivery_event_counts_respect_the_window(tmp_path):
    store = DeliveryStore(str(tmp_path / "hooks.db"))
    store.initialize()
    for index, event in enumerate(["pull_request", "pull_request", "check_suite"]):
        assert store.record(f"d-{index}", event, {"action": "opened"})
    assert store.record("d-0", "pull_request", {}) is False
    connection(str(store.path)).execute(
        "UPDATE deliveries SET received_at='2000-01-01 00:00:00' WHERE delivery_id='d-2'"
    )
    assert store.event_counts(24) == [{"label": "pull_request", "value": 2}]
