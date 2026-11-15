/** SQLite schema, connection cache and row mapping for the durable job queue (bun:sqlite). */
import { Database } from "bun:sqlite";
import { statSync } from "node:fs";

export const SCHEMA = `
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    payload TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_run_at REAL NOT NULL,
    lease_token TEXT,
    lease_expires_at REAL,
    reprocess_pending INTEGER NOT NULL DEFAULT 0,
    task_id TEXT,
    repo TEXT,
    sha TEXT,
    decision TEXT,
    next_action TEXT,
    last_error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(kind, key)
)`;
export const INDEXES = [
  "CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs(status, priority DESC, next_run_at)",
  "CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC)",
  "CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at DESC)",
  "CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at)",
];
export const DROPPED_INDEXES = ["idx_jobs_status", "idx_jobs_kind_key"];

export type Job = {
  id: string; kind: string; key: string; payload: Record<string, any>;
  priority: number; status: string; attempts: number; max_attempts: number;
  next_run_at: number; lease_token: string | null; lease_expires_at: number | null;
  reprocess_pending: boolean; task_id: string | null; repo: string | null;
  sha: string | null; decision: string | null; next_action: string | null;
  last_error: string | null; created_at: number; updated_at: number;
};

export function rowToJob(row: any): Job {
  let payload: Record<string, any> = {};
  try { payload = JSON.parse(row.payload); } catch { /* keep {} */ }
  return { ...row, payload, reprocess_pending: !!row.reprocess_pending };
}

export function openConnection(path: string): Database {
  const db = new Database(path, { create: true, strict: true });
  db.exec("PRAGMA busy_timeout=30000");
  return db;
}

const MAX_CACHED = 8;
const cache = new Map<string, { inode: number; db: Database }>();
const inodeOf = (p: string) => { try { return statSync(p).ino; } catch { return null; } };

/** Cached connection per path; reopened when the file is replaced. Never close it. */
export function connection(path: string): Database {
  const inode = inodeOf(path);
  const hit = cache.get(path);
  if (hit) {
    if (inode !== null && hit.inode === inode) return hit.db;
    hit.db.close();
    cache.delete(path);
  }
  while (cache.size >= MAX_CACHED) {
    const first = cache.keys().next().value as string;
    cache.get(first)!.db.close();
    cache.delete(first);
  }
  const db = openConnection(path);
  cache.set(path, { inode: inodeOf(path) ?? -1, db });
  return db;
}

export function closeAllConnections(): void {
  for (const { db } of cache.values()) db.close();
  cache.clear();
}
