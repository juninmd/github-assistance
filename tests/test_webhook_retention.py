import os
import sqlite3
import threading
import time
from pathlib import Path

from src.webhooks.retention import purge_deliveries, run_retention
from src.webhooks.store import DeliveryStore

DAY = 86400
NOW = 1_800_000_000.0


def _store(tmp_path: Path) -> tuple[DeliveryStore, str]:
    path = str(tmp_path / "webhooks.db")
    store = DeliveryStore(path)
    store.initialize()
    return store, path


def _insert(path: str, delivery_id: str, age_days: float, payload_bytes: int = 20_000) -> None:
    received = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(NOW - age_days * DAY))
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO deliveries (delivery_id, event, payload, received_at) VALUES (?, 'x', ?, ?)",
            (delivery_id, "p" * payload_bytes, received),
        )


def _ids(path: str) -> set[str]:
    with sqlite3.connect(path) as db:
        return {row[0] for row in db.execute("SELECT delivery_id FROM deliveries")}


def test_purge_keeps_recent_and_deletes_old_across_batches(tmp_path):
    _, path = _store(tmp_path)
    for i in range(25):
        _insert(path, f"old-{i}", age_days=10 + i)
    _insert(path, "edge-in", age_days=6.9)
    _insert(path, "edge-out", age_days=7.1)
    _insert(path, "fresh", age_days=0)

    result = purge_deliveries(path, 7, now=NOW, batch=4)

    assert result["deleted"] == 26
    assert _ids(path) == {"edge-in", "fresh"}


def test_vacuum_returns_space_to_filesystem(tmp_path):
    _, path = _store(tmp_path)
    for i in range(200):
        _insert(path, f"old-{i}", age_days=30)
    _insert(path, "fresh", age_days=0)
    before = os.path.getsize(path)

    result = purge_deliveries(path, 7, now=NOW)

    assert result["vacuumed"] is True
    assert result["size_bytes"] < before / 10
    assert not os.path.exists(path + "-wal") or os.path.getsize(path + "-wal") == 0


def test_no_vacuum_when_little_is_free(tmp_path):
    _, path = _store(tmp_path)
    for i in range(50):
        _insert(path, f"fresh-{i}", age_days=1)

    result = purge_deliveries(path, 7, now=NOW)

    assert result == {"deleted": 0, "vacuumed": False, "size_bytes": os.path.getsize(path)}


def test_purge_is_idempotent_and_reuses_the_index(tmp_path):
    _, path = _store(tmp_path)
    _insert(path, "old", age_days=30)

    purge_deliveries(path, 7, now=NOW)
    second = purge_deliveries(path, 7, now=NOW)

    assert second["deleted"] == 0
    with sqlite3.connect(path) as db:
        plan = db.execute(
            "EXPLAIN QUERY PLAN SELECT rowid FROM deliveries WHERE received_at < '2000-01-01'"
        ).fetchall()
    assert "idx_deliveries_received_at" in str(plan)


def test_purged_delivery_id_is_accepted_again_but_recent_one_stays_deduped(tmp_path):
    store, path = _store(tmp_path)
    store.record("old", "push", {})
    store.record("fresh", "push", {})
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE deliveries SET received_at = '2000-01-01 00:00:00' WHERE delivery_id = 'old'"
        )

    purge_deliveries(path, 7, now=time.time())

    assert store.record("fresh", "push", {}) is False
    assert store.record("old", "push", {}) is True


def test_run_retention_survives_failures_and_stops(tmp_path):
    stop = threading.Event()
    thread = threading.Thread(
        target=run_retention,
        args=(str(tmp_path / "missing" / "no.db"), 7, 0.01, stop),
        kwargs={"initial_delay": 0.01},
    )
    thread.start()
    time.sleep(0.1)
    assert thread.is_alive()
    stop.set()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_server_lifespan_starts_and_stops_purge_thread(tmp_path):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from src.config.settings import Settings
    from src.webhooks.server import create_app

    settings = replace(
        Settings(github_token="unused", webhook_database_path=str(tmp_path / "w.db")),
        worker_enabled=False,
    )
    app = create_app(settings)
    with TestClient(app):
        thread = app.state.purge_thread
        assert thread.is_alive()
    assert not thread.is_alive()

    off = create_app(replace(settings, webhook_purge_enabled=False))
    with TestClient(off):
        assert off.state.purge_thread is None


def test_settings_defaults_and_validation(monkeypatch):
    import pytest

    from src.config.settings import Settings

    monkeypatch.setenv("GITHUB_TOKEN", "x")
    settings = Settings.from_env()
    assert (settings.webhook_purge_enabled, settings.webhook_retention_days) == (True, 3)
    monkeypatch.setenv("WEBHOOK_RETENTION_DAYS", "0")
    with pytest.raises(ValueError, match="WEBHOOK_RETENTION_DAYS"):
        Settings.from_env()
