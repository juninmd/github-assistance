/** Durable webhook delivery state + atomic webhook-to-job persistence. */
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { JobStore } from "../queue/store.ts";
import { connection } from "../queue/schema.ts";

export class DeliveryStore {
  jobs: JobStore;
  constructor(public path: string) { this.jobs = new JobStore(path); }
  private db() { return connection(this.path); }

  initialize(): void {
    mkdirSync(dirname(this.path), { recursive: true });
    this.jobs.initialize();
    this.db().exec(`CREATE TABLE IF NOT EXISTS deliveries (
      delivery_id TEXT PRIMARY KEY, event TEXT NOT NULL, action TEXT, repository TEXT,
      payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'observed',
      received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`);
    this.db().exec("CREATE INDEX IF NOT EXISTS idx_deliveries_received_at ON deliveries(received_at)");
  }

  /** Persist delivery + PR jobs in one transaction. Duplicate deliveries never create or reopen jobs. */
  recordAndEnqueue(deliveryId: string, event: string, payload: Record<string, any>, prRefs: string[],
    o: { mode: string; priority?: number; now?: number }): [boolean, string[]] {
    const db = this.db();
    const action = payload.action ?? null, repository = payload.repository?.full_name ?? null;
    const ids: string[] = [];
    db.exec("BEGIN IMMEDIATE");
    try {
      const r = db.query("INSERT OR IGNORE INTO deliveries (delivery_id, event, action, repository, payload) VALUES (?,?,?,?,?)")
        .run(deliveryId, event, action, repository, JSON.stringify(payload));
      const created = r.changes > 0;
      if (created) {
        const jp = { mode: o.mode, event, action, delivery_id: deliveryId };
        for (const ref of prRefs) {
          const [id] = this.jobs.upsert(db, "pr", ref, jp, { priority: o.priority ?? 0, repo: ref.split("#", 1)[0], now: o.now });
          ids.push(id);
        }
      }
      db.exec("COMMIT");
      return [created, ids];
    } catch (e) { db.exec("ROLLBACK"); throw e; }
  }

  eventCounts(hours: number, now = Date.now() / 1000) {
    const cutoff = new Date((now - hours * 3600) * 1000).toISOString().slice(0, 19).replace("T", " ");
    return (this.db().query("SELECT event AS label, COUNT(*) AS n FROM deliveries WHERE received_at >= ? GROUP BY event ORDER BY n DESC, event").all(cutoff) as any[])
      .map((r) => ({ label: r.label, value: r.n }));
  }

  ready(): boolean { try { this.db().query("SELECT 1").get(); return true; } catch { return false; } }
}
