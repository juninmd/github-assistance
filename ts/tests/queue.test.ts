import { expect, test } from "bun:test";
import { writeFileSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { queueOverview } from "../src/queue/overview.ts";
import { connection, closeAllConnections } from "../src/queue/schema.ts";
import { QueueWorker } from "../src/queue/worker.ts";
import { getJob, newStore, tmp } from "./helpers.ts";

test("enqueue deduplicates by key", () => {
  const s = newStore();
  const [a, c1] = s.enqueue("pr", "juninmd/repo#1", { event: "opened" });
  const [b, c2] = s.enqueue("pr", "juninmd/repo#1", { event: "check_suite" });
  expect([c1, c2, a === b]).toEqual([true, false, true]);
  const j = getJob(s, a);
  expect(j.status).toBe("pending");
  expect(j.payload.event).toBe("check_suite");
});

test("restart recovers running job without duplication", async () => {
  const s = newStore();
  const [id] = s.enqueue("pr", "juninmd/repo#2", { event: "opened" }, { now: 999 });
  const claimed = s.claim(1000);
  expect(claimed.length).toBe(1);
  expect(claimed[0].status).toBe("running");
  expect(s.recoverStale(1000 + 301)).toBe(1);
  expect(getJob(s, id).status).toBe("pending");
  const seen: string[] = [];
  const w = new QueueWorker(s, (j) => { seen.push(j.id); return { status: "succeeded" }; }, { clock: () => 2000 });
  await w.runOnce(2000);
  expect(seen).toEqual([id]);
  expect(getJob(s, id).status).toBe("succeeded");
});

test("claim honors configured lease", () => {
  const s = newStore();
  s.enqueue("pr", "juninmd/repo#4", {}, { now: 1 });
  s.claim(1, 1, 900);
  expect(s.recoverStale(1 + 301)).toBe(0);
  expect(s.recoverStale(1 + 901)).toBe(1);
});

test("complete from expired lease does not overwrite new owner", () => {
  const s = newStore();
  const [id] = s.enqueue("pr", "juninmd/repo#5", {}, { now: 1 });
  const stale = s.claim(1, 1, 10)[0];
  s.recoverStale(20);
  const fresh = s.claim(20, 1, 10)[0];
  expect(s.complete(id, "blocked", { now: 21, lease_token: stale.lease_token })).toEqual({});
  expect(getJob(s, id).status).toBe("running");
  s.complete(id, "succeeded", { now: 22, lease_token: fresh.lease_token });
  expect(getJob(s, id).status).toBe("succeeded");
});

test("worker leases each job from its own claim time", async () => {
  const s = newStore();
  for (const n of [1, 2, 3]) s.enqueue("pr", `juninmd/repo#${n}`, {}, { now: 0 });
  let clock = 100;
  const leases: (number | null)[] = [];
  const w = new QueueWorker(s, (j) => { leases.push(j.lease_expires_at); clock += 150; return { status: "succeeded" }; },
    { leaseSeconds: 300, limit: 3, clock: () => clock });
  expect((await w.runOnce()).length).toBe(3);
  expect(leases).toEqual([400, 550, 700]);
});

test("event during processing guarantees re-evaluation", async () => {
  const s = newStore();
  const [id] = s.enqueue("pr", "juninmd/repo#3", { event: "opened" }, { now: 1 });
  expect(s.claim(1).length).toBe(1);
  s.enqueue("pr", "juninmd/repo#3", { event: "check_suite" }, { now: 2 });
  expect(getJob(s, id).reprocess_pending).toBe(true);
  const done: any = s.complete(id, "succeeded", { now: 2 });
  expect(done.status).toBe("pending");
  expect(done.next_run_at).toBe(2);
  const rounds: string[] = [];
  await new QueueWorker(s, (j) => { rounds.push(j.payload.event); return { status: "succeeded" }; }, { clock: () => 2 }).runOnce(2);
  expect(rounds).toEqual(["check_suite"]);
  expect(getJob(s, id).status).toBe("succeeded");
});

test("event coalesced during a run starts a fresh attempt budget", async () => {
  const s = newStore();
  const [id] = s.enqueue("pr", "juninmd/repo#6", {}, { max_attempts: 2, now: 1 });
  expect(s.claim(1).length).toBe(1);
  s.enqueue("pr", "juninmd/repo#6", {}, { now: 2 });
  const requeued: any = s.complete(id, "succeeded", { now: 2 });
  // A re-evaluation is not a retry: it must not look "retrying" nor eat the retry budget.
  expect([requeued.status, requeued.attempts]).toEqual(["pending", 0]);
  s.claim(2);
  const failed: any = s.complete(id, "failed", { now: 3, error: "boom" });
  expect(failed.status).toBe("pending");
});

test("failed job retries then blocks", async () => {
  const s = newStore();
  const [id] = s.enqueue("pr", "juninmd/repo#4", {}, { max_attempts: 2, now: 1 });
  const w = new QueueWorker(s, () => ({ status: "failed", error: "boom" }), { clock: () => 1 });
  await w.runOnce(1);
  expect(getJob(s, id).status).toBe("pending");
  await w.runOnce(1000);
  const j = getJob(s, id);
  expect([j.status, j.attempts]).toEqual(["blocked", 2]);
});

test("handler exception becomes failure; unknown status treated as failed", async () => {
  const s = newStore();
  const [a] = s.enqueue("pr", "x/y#1", {}, { max_attempts: 1, now: 1 });
  await new QueueWorker(s, () => { throw new Error("kaboom"); }).runOnce(1);
  expect(getJob(s, a).last_error).toBe("kaboom");
  const [b] = s.enqueue("pr", "x/y#2", {}, { max_attempts: 1, now: 1 });
  await new QueueWorker(s, () => ({ status: "weird" })).runOnce(1);
  expect(getJob(s, b).last_error).toContain("unknown status");
});

test("reprocess reopens finished job", () => {
  const s = newStore();
  const [id] = s.enqueue("pr", "juninmd/repo#5", {}, { now: 1 });
  s.complete(id, "succeeded", { now: 2 });
  expect(getJob(s, id).status).toBe("succeeded");
  expect(s.reprocess("pr", "juninmd/repo#5", 3)).toBe(true);
  expect(getJob(s, id).status).toBe("pending");
});

// --- storage -----------------------------------------------------------------
test("connection is cached per file and reopened when the file is replaced", () => {
  const dir = tmp();
  const p = join(dir, "a.db");
  const a = connection(p);
  expect(connection(p)).toBe(a);
  a.exec("CREATE TABLE t(x)");
  closeAllConnections();
  unlinkSync(p);
  writeFileSync(p, "");
  const b = connection(p);
  expect(b).not.toBe(a);
});

test("connection cache is bounded", () => {
  const dir = tmp();
  for (let i = 0; i < 12; i++) connection(join(dir, `${i}.db`));
  // no throw; oldest evicted silently
  expect(connection(join(dir, "11.db"))).toBeTruthy();
});

test("initialize migrates superseded indexes", () => {
  const s = newStore();
  const db = connection(s.path);
  db.exec("CREATE INDEX idx_jobs_status ON jobs(status)");
  db.exec("CREATE INDEX idx_jobs_kind_key ON jobs(kind, key)");
  s.initialize();
  const names = (db.query("SELECT name FROM sqlite_master WHERE type='index'").all() as any[]).map((r) => r.name);
  expect(names).not.toContain("idx_jobs_status");
  expect(names).not.toContain("idx_jobs_kind_key");
  expect(names).toContain("idx_jobs_claim");
});

test("claim returns highest priority first", () => {
  const s = newStore();
  s.enqueue("pr", "a/b#1", {}, { priority: 0, now: 1 });
  s.enqueue("pr", "a/b#2", {}, { priority: 10, now: 2 });
  s.enqueue("pr", "a/b#3", {}, { priority: 5, now: 0 });
  expect(s.claim(5, 3).map((j) => j.key)).toEqual(["a/b#2", "a/b#3", "a/b#1"]);
});

test("list filters in SQL and paginates", () => {
  const s = newStore();
  for (let i = 0; i < 5; i++) s.enqueue("pr", `acme/web#${i}`, {}, { repo: "acme/web", now: i });
  s.enqueue("pr", "acme/api#1", {}, { repo: "acme/api", now: 9 });
  expect(s.count({ repo: "acme/web" })).toBe(5);
  expect(s.list({ repo: "acme/web", limit: 2, offset: 1 }).length).toBe(2);
  expect(s.list({ search: "API" })[0].key).toBe("acme/api#1");
  expect(s.list({ status: "blocked" })).toEqual([]);
});

test("overview aggregates backlog, window and rankings; empty queue ok", () => {
  const empty = queueOverview(newStore().path, { hours: 24 * 7, now: 1_800_000_000 });
  expect(empty.window.success_rate).toBeNull();
  expect(empty.throughput.length).toBe(28);
  const s = newStore();
  const now = 1_800_000_000;
  const [a] = s.enqueue("pr", "a/b#1", {}, { repo: "a/b", now: now - 100 });
  s.complete(a, "succeeded", { decision: "merged", now: now - 50 });
  s.enqueue("pr", "a/b#2", {}, { repo: "a/b", now: now - 100 });
  const o = queueOverview(s.path, { hours: 24, now });
  expect(o.totals).toEqual({ succeeded: 1, pending: 1 });
  expect(o.backlog.due).toBe(1);
  expect(o.window.success_rate).toBe(1);
  expect(o.decisions).toContainEqual({ label: "merged", value: 1 });
  expect(o.repositories[0].label).toBe("a/b");
});
