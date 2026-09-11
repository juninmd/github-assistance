"""Durable queue: restart recovery, event-coalescing, retries and idempotency."""

from src.queue.store import JobStore
from src.queue.worker import QueueWorker


def _store(tmp_path):
    store = JobStore(str(tmp_path / "queue.db"))
    store.initialize()
    return store


def _get(store, jid):
    job = store.get(jid)
    assert job is not None
    return job


def test_enqueue_deduplicates_by_key(tmp_path):
    store = _store(tmp_path)
    jid1, created1 = store.enqueue("pr", "juninmd/repo#1", {"event": "opened"})
    jid2, created2 = store.enqueue("pr", "juninmd/repo#1", {"event": "check_suite"})
    assert created1 is True
    assert created2 is False
    assert jid1 == jid2
    job = _get(store, jid1)
    assert job["status"] == "pending"
    assert job["payload"]["event"] == "check_suite"


def test_restart_recovers_running_job_without_duplication(tmp_path):
    store = _store(tmp_path)
    store.initialize()
    jid, _ = store.enqueue("pr", "juninmd/repo#2", {"event": "opened"}, now=999.0)
    claimed = store.claim(now=1000.0)
    assert len(claimed) == 1 and claimed[0]["status"] == "running"

    recovered = store.recover_stale(now=1000.0 + 301)
    assert recovered == 1
    assert _get(store, jid)["status"] == "pending"

    # A second worker that would have claimed before the restart is not running;
    # recovering + re-claiming must process exactly one handler call.
    seen = []

    def handler(job):
        seen.append(job["id"])
        return {"status": "succeeded"}

    worker = QueueWorker(store, handler, clock=lambda: 2000.0)
    worker.run_once(now=2000.0)
    assert seen == [jid]
    assert _get(store, jid)["status"] == "succeeded"


def test_claim_honors_configured_lease(tmp_path):
    store = _store(tmp_path)
    store.enqueue("pr", "juninmd/repo#4", {}, now=1.0)
    store.claim(now=1.0, lease_seconds=900)
    assert store.recover_stale(now=1.0 + 301) == 0
    assert store.recover_stale(now=1.0 + 901) == 1


def test_complete_from_expired_lease_does_not_overwrite_new_owner(tmp_path):
    store = _store(tmp_path)
    jid, _ = store.enqueue("pr", "juninmd/repo#5", {}, now=1.0)
    stale = store.claim(now=1.0, lease_seconds=10)[0]
    store.recover_stale(now=20.0)
    fresh = store.claim(now=20.0, lease_seconds=10)[0]

    assert store.complete(jid, "blocked", now=21.0, lease_token=stale["lease_token"]) == {}
    assert _get(store, jid)["status"] == "running"
    store.complete(jid, "succeeded", now=22.0, lease_token=fresh["lease_token"])
    assert _get(store, jid)["status"] == "succeeded"


def test_worker_leases_each_job_from_its_own_claim_time(tmp_path):
    store = _store(tmp_path)
    for n in (1, 2, 3):
        store.enqueue("pr", f"juninmd/repo#{n}", {}, now=0.0)
    clock = [100.0]
    leases = []

    def handler(job):
        leases.append(job["lease_expires_at"])
        clock[0] += 150
        return {"status": "succeeded"}

    worker = QueueWorker(store, handler, lease_seconds=300, limit=3, clock=lambda: clock[0])
    assert len(worker.run_once()) == 3
    # A shared batch lease would give job 3 an already-expired lease (400).
    assert leases == [400.0, 550.0, 700.0]


def test_event_during_processing_guarantees_reevaluation(tmp_path):
    store = _store(tmp_path)
    store.initialize()
    jid, _ = store.enqueue("pr", "juninmd/repo#3", {"event": "opened"}, now=1.0)
    claimed = store.claim(now=1.0)
    assert len(claimed) == 1

    # New event arrives while job is running -> reprocess_pending is set.
    store.enqueue("pr", "juninmd/repo#3", {"event": "check_suite"}, now=2.0)
    assert _get(store, jid)["reprocess_pending"] is True

    rounds = []

    def handler(job):
        rounds.append(job["payload"]["event"])
        return {"status": "succeeded", "decision": "done", "next_action": "merge"}

    # The worker that owns the lease finishes round 1; complete() must schedule
    # a fresh round for the event that arrived mid-processing.
    completed = store.complete(jid, "succeeded", now=2.0)
    assert completed["status"] == "pending"
    assert completed["next_run_at"] == 2.0

    worker = QueueWorker(store, handler, clock=lambda: 2.0)
    worker.run_once(now=2.0)
    assert rounds == ["check_suite"]
    assert _get(store, jid)["status"] == "succeeded"


def test_failed_job_retries_then_blocks(tmp_path):
    store = _store(tmp_path)
    store.initialize()
    jid, _ = store.enqueue("pr", "juninmd/repo#4", {}, max_attempts=2, now=1.0)

    worker = QueueWorker(
        store, lambda _j: {"status": "failed", "error": "boom"}, clock=lambda: 1.0
    )
    worker.run_once(now=1.0)
    assert _get(store, jid)["status"] == "pending"

    worker.run_once(now=1000.0)
    assert _get(store, jid)["status"] == "blocked"
    assert _get(store, jid)["attempts"] == 2


def test_reprocess_reopens_finished_job(tmp_path):
    store = _store(tmp_path)
    store.initialize()
    jid, _ = store.enqueue("pr", "juninmd/repo#5", {}, now=1.0)
    store.complete(jid, "succeeded", now=2.0)
    assert _get(store, jid)["status"] == "succeeded"
    assert store.reprocess("pr", "juninmd/repo#5", now=3.0) is True
    assert _get(store, jid)["status"] == "pending"


def test_worker_observe_handler_has_no_external_effects(tmp_path):
    store = _store(tmp_path)
    store.initialize()
    store.enqueue("pr", "juninmd/repo#6", {}, now=1.0)
    worker = QueueWorker(
        store,
        lambda job: {
            "status": "succeeded",
            "decision": "observed",
            "next_action": "observe",
        },
        clock=lambda: 1.0,
    )
    worker.run_once(now=1.0)
    job = store.list_jobs()[0]
    assert job["status"] == "succeeded"
    assert job["decision"] == "observed"
