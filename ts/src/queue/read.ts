/** Read-only queries over the durable job queue. */
import { connection, rowToJob, type Job } from "./schema.ts";

const EQ = ["status", "kind", "repo", "key"] as const;
export type Filters = { status?: string; kind?: string; repo?: string; key?: string; search?: string };

function where(f: Filters, cols: readonly string[] = EQ): [string, any[]] {
  const clauses: string[] = [];
  const params: any[] = [];
  for (const c of cols) {
    const v = (f as any)[c];
    if (v) { clauses.push(`${c}=?`); params.push(v); }
  }
  if (f.search) { clauses.push("instr(lower(key), lower(?)) > 0"); params.push(f.search); }
  return [clauses.length ? " WHERE " + clauses.join(" AND ") : "", params];
}

export function getJob(path: string, id: string): Job | null {
  const row = connection(path).query("SELECT * FROM jobs WHERE id=?").get(id);
  return row ? rowToJob(row) : null;
}

export function listJobs(path: string, f: Filters & { limit?: number; offset?: number } = {}): Job[] {
  const [w, p] = where(f);
  const rows = connection(path)
    .query(`SELECT * FROM jobs${w} ORDER BY created_at DESC LIMIT ? OFFSET ?`)
    .all(...p, f.limit ?? 100, f.offset ?? 0);
  return rows.map(rowToJob);
}

export function countJobs(path: string, f: Filters = {}): number {
  const [w, p] = where(f, ["status", "kind", "repo"]);
  const row = connection(path).query(`SELECT COUNT(*) AS n FROM jobs${w}`).get(...p) as any;
  return row.n;
}

export function jobStats(path: string): Record<string, number> {
  const rows = connection(path).query("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").all() as any[];
  return Object.fromEntries(rows.map((r) => [r.status, r.n]));
}
