/** Aggregated queue metrics for the dashboard (`GET /api/overview`). */
import { connection } from "./schema.ts";

const HOUR = 3600;
export const MAX_WINDOW_HOURS = 24 * 7;
const TOP_N = 8;
const OUTCOME = `CASE WHEN status IN ('succeeded','blocked') THEN status WHEN status='pending' AND attempts>0 THEN 'retrying' END`;
export const bucketSeconds = (hours: number) => (hours <= 48 ? HOUR : 6 * HOUR);

export function queueOverview(path: string, o: { hours?: number; now?: number } = {}) {
  const now = o.now ?? Date.now() / 1000;
  const hours = Math.max(1, Math.min(o.hours ?? 24, MAX_WINDOW_HOURS));
  const step = bucketSeconds(hours);
  const buckets = Math.floor((hours * HOUR) / step);
  const start = (Math.floor(now / step) + 1) * step - buckets * step;
  const db = connection(path);
  const totals: Record<string, number> = {};
  for (const r of db.query("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").all() as any[]) totals[r.status] = r.n;
  const backlog = db.query(
    `SELECT COUNT(*) FILTER (WHERE next_run_at <= $now) AS due, COUNT(*) FILTER (WHERE next_run_at > $now) AS scheduled,
     COUNT(*) FILTER (WHERE attempts > 0) AS retrying, MIN(next_run_at) AS oldest FROM jobs WHERE status='pending'`,
  ).get({ now }) as any;
  const series: any[] = Array.from({ length: buckets }, (_, i) => ({ start: start + i * step, succeeded: 0, blocked: 0, retrying: 0 }));
  const rows = db.query(
    `SELECT CAST((updated_at - ?) / ? AS INTEGER) AS bucket, ${OUTCOME} AS outcome, COUNT(*) AS n
     FROM jobs WHERE updated_at >= ? GROUP BY bucket, outcome`,
  ).all(start, step, start) as any[];
  for (const r of rows) if (r.outcome && r.bucket >= 0 && r.bucket < buckets) series[r.bucket][r.outcome] = r.n;
  const sum = (k: string) => series.reduce((a, p) => a + p[k], 0);
  const succeeded = sum("succeeded"), blocked = sum("blocked"), finished = succeeded + blocked;
  const oldest = backlog.oldest;
  const ranked = (expr: string) =>
    (db.query(`SELECT ${expr} AS label, COUNT(*) AS n FROM jobs WHERE updated_at >= ? GROUP BY label ORDER BY n DESC, label LIMIT ?`).all(start, TOP_N) as any[])
      .map((r) => ({ label: r.label, value: r.n }));
  const repositories = (db.query(
    `SELECT COALESCE(repo,'') AS label, COUNT(*) AS n, COUNT(*) FILTER (WHERE status='succeeded') AS succeeded,
     COUNT(*) FILTER (WHERE status='blocked') AS blocked, COUNT(*) FILTER (WHERE status IN ('pending','running')) AS open
     FROM jobs WHERE updated_at >= ? GROUP BY label ORDER BY n DESC, label LIMIT ?`,
  ).all(start, TOP_N) as any[]).map((r) => ({ label: r.label, value: r.n, succeeded: r.succeeded, blocked: r.blocked, open: r.open }));
  return {
    generated_at: now, window_hours: hours, bucket_seconds: step, totals,
    backlog: {
      due: backlog.due, scheduled: backlog.scheduled, retrying: backlog.retrying,
      running: totals.running ?? 0,
      oldest_due_age_seconds: oldest && oldest <= now ? Math.max(0, now - oldest) : 0,
    },
    window: { succeeded, blocked, retrying: sum("retrying"), success_rate: finished ? Math.round((succeeded / finished) * 1e4) / 1e4 : null },
    throughput: series,
    decisions: ranked("COALESCE(decision, '')"),
    repositories,
  };
}
