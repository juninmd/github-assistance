/**
 * SQLite-backed durable job queue with leases, retries and idempotency.
 * One row per (kind, key); new events coalesce and set reprocess_pending.
 */
import { randomUUID } from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { Database } from "bun:sqlite";
import { completeJob, reprocessJob, type CompleteOpts } from "./outcome.ts";
import { countJobs, getJob, jobStats, listJobs, type Filters } from "./read.ts";
import { DROPPED_INDEXES, INDEXES, SCHEMA, connection, rowToJob, type Job } from "./schema.ts";

export type EnqueueOpts = { priority?: number; max_attempts?: number; repo?: string | null; now?: number };
const nowS = () => Date.now() / 1000;

export class JobStore {
  constructor(public path: string) {}

  initialize(): void {
    mkdirSync(dirname(this.path), { recursive: true });
    const db = connection(this.path);
    db.exec("PRAGMA journal_mode=WAL");
    db.exec(SCHEMA);
    for (const n of DROPPED_INDEXES) db.exec(`DROP INDEX IF EXISTS ${n}`);
    for (const s of INDEXES) db.exec(s);
  }

  enqueue(kind: string, key: string, payload: Record<string, any> = {}, o: EnqueueOpts = {}): [string, boolean] {
    const db = connection(this.path);
    db.exec("BEGIN IMMEDIATE");
    try {
      const r = this.upsert(db, kind, key, payload, o);
      db.exec("COMMIT");
      return r;
    } catch (e) {
      db.exec("ROLLBACK");
      throw e;
    }
  }

  /** Upsert inside an already-open transaction. Returns [job_id, created]. */
  upsert(db: Database, kind: string, key: string, payload: Record<string, any> | null, o: EnqueueOpts = {}): [string, boolean] {
    const now = o.now ?? nowS();
    const json = JSON.stringify(payload ?? {});
    const row = db.query("SELECT id, status FROM jobs WHERE kind=? AND key=?").get(kind, key) as any;
    if (row) {
      if (row.status === "pending" || row.status === "running") {
        db.query("UPDATE jobs SET payload=?, reprocess_pending=1, updated_at=? WHERE id=?").run(json, now, row.id);
      } else {
        db.query(
          `UPDATE jobs SET payload=?, status='pending', attempts=0, reprocess_pending=0, last_error=NULL,
           next_run_at=?, lease_token=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?`,
        ).run(json, now, now, row.id);
      }
      return [row.id, false];
    }
    const id = randomUUID().replace(/-/g, "");
    db.query(
      `INSERT INTO jobs (id, kind, key, payload, priority, status, attempts, max_attempts, next_run_at, repo, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?, ?)`,
    ).run(id, kind, key, json, o.priority ?? 0, o.max_attempts ?? 3, now, o.repo ?? null, now, now);
    return [id, true];
  }

  claim(now = nowS(), limit = 1, leaseSeconds = 300): Job[] {
    const rows = connection(this.path).query(
      `UPDATE jobs SET status='running', lease_token=?, lease_expires_at=?, updated_at=?
       WHERE id IN (SELECT id FROM jobs WHERE status='pending' AND next_run_at<=?
                    ORDER BY priority DESC, next_run_at ASC LIMIT ?) RETURNING *`,
    ).all(randomUUID().replace(/-/g, ""), now + leaseSeconds, now, now, limit) as any[];
    rows.sort((a, b) => b.priority - a.priority || a.next_run_at - b.next_run_at);
    return rows.map(rowToJob);
  }

  recoverStale(now = nowS()): number {
    return connection(this.path).query(
      `UPDATE jobs SET status='pending', lease_token=NULL, lease_expires_at=NULL, updated_at=?
       WHERE status='running' AND (lease_expires_at IS NULL OR lease_expires_at < ?)`,
    ).run(now, now).changes;
  }

  complete(id: string, status: string, o: CompleteOpts = {}) { return completeJob(this.path, id, status, { now: nowS(), ...o }); }
  reprocess(kind: string, key: string, now?: number) { return reprocessJob(this.path, kind, key, now); }
  get(id: string) { return getJob(this.path, id); }
  list(f: Filters & { limit?: number; offset?: number } = {}) { return listJobs(this.path, f); }
  count(f: Filters = {}) { return countJobs(this.path, f); }
  stats() { return jobStats(this.path); }
}
