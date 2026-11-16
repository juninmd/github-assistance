/** Job completion/retry transitions for the durable queue. */
import { connection, rowToJob, type Job } from "./schema.ts";

const FINAL = ["succeeded", "blocked"];

export function nextStatus(
  status: string, attempts: number, maxAttempts: number, reprocessPending: number | boolean,
): [string, boolean] {
  if (reprocessPending && FINAL.includes(status)) return ["pending", true];
  if (status === "failed") return [attempts + 1 < maxAttempts ? "pending" : "blocked", false];
  return [status, false];
}

export type CompleteOpts = {
  error?: string | null; decision?: string | null; next_action?: string | null;
  sha?: string | null; task_id?: string | null; now?: number;
  backoff_seconds?: number; lease_token?: string | null;
};

/** Returns {} when the job is unknown or the lease no longer belongs to the caller. */
export function completeJob(path: string, jobId: string, status: string, o: CompleteOpts = {}): Job | {} {
  const now = o.now ?? Date.now() / 1000;
  const db = connection(path);
  db.exec("BEGIN IMMEDIATE");
  try {
    const row = db.query(
      "SELECT attempts, max_attempts, reprocess_pending, lease_token FROM jobs WHERE id=?",
    ).get(jobId) as any;
    if (!row || (o.lease_token != null && row.lease_token !== o.lease_token)) {
      db.exec("ROLLBACK");
      return {};
    }
    const [next, immediate] = nextStatus(status, row.attempts, row.max_attempts, row.reprocess_pending);
    const retrying = next === "pending" ? 1 : 0;
    const delay = immediate ? 0 : (o.backoff_seconds ?? 60) * (row.attempts + 1);
    const updated = db.query(
      `UPDATE jobs SET status=?, attempts=?, lease_token=NULL, lease_expires_at=NULL,
       reprocess_pending=CASE WHEN ? THEN 0 ELSE reprocess_pending END,
       next_run_at=CASE WHEN ? THEN ? ELSE next_run_at END,
       last_error=?, decision=?, next_action=?, sha=?, task_id=?, updated_at=?
       WHERE id=? RETURNING *`,
    ).all(
      next, row.attempts + 1, retrying, retrying, now + delay, o.error ?? null, o.decision ?? null,
      o.next_action ?? null, o.sha ?? null, o.task_id ?? null, now, jobId,
    ) as any[];
    db.exec("COMMIT");
    return updated[0] ? rowToJob(updated[0]) : {};
  } catch (e) {
    db.exec("ROLLBACK");
    throw e;
  }
}

export function reprocessJob(path: string, kind: string, key: string, now = Date.now() / 1000): boolean {
  const r = connection(path).query(
    "UPDATE jobs SET status='pending', attempts=0, reprocess_pending=0, next_run_at=?, lease_token=NULL, updated_at=? WHERE kind=? AND key=?",
  ).run(now, now, kind, key);
  return r.changes > 0;
}
