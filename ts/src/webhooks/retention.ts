/** Retention for webhook deliveries: bounded batch delete, then VACUUM. */
import { statSync } from "node:fs";
import { getLogger } from "../utils/logger.ts";
import { openConnection } from "../queue/schema.ts";

const log = getLogger("webhook-retention");
export const BATCH_ROWS = 500;
const VACUUM_MIN_FREE_RATIO = 0.25;

export function purgeDeliveries(path: string, retentionDays: number, o: { now?: number; batch?: number } = {}) {
  const at = o.now ?? Date.now() / 1000, batch = o.batch ?? BATCH_ROWS;
  const cutoff = new Date((at - retentionDays * 86400) * 1000).toISOString().slice(0, 19).replace("T", " ");
  const db = openConnection(path);
  try {
    db.exec("CREATE INDEX IF NOT EXISTS idx_deliveries_received_at ON deliveries(received_at)");
    let deleted = 0;
    for (;;) {
      const n = db.query("DELETE FROM deliveries WHERE rowid IN (SELECT rowid FROM deliveries WHERE received_at < ? LIMIT ?)").run(cutoff, batch).changes;
      deleted += n;
      if (n < batch) break;
    }
    const pages = (db.query("PRAGMA page_count").get() as any).page_count;
    const free = (db.query("PRAGMA freelist_count").get() as any).freelist_count;
    const vacuumed = !!pages && free / pages >= VACUUM_MIN_FREE_RATIO;
    if (vacuumed) db.exec("VACUUM");
    db.exec("PRAGMA wal_checkpoint(TRUNCATE)");
    return { deleted, vacuumed, size_bytes: statSync(path).size };
  } finally { db.close(); }
}

/** Purge shortly after start, then every interval. Returns a stop function. */
export function startRetention(path: string, days: number, intervalSeconds: number, initialDelay = 30): () => void {
  let timer: ReturnType<typeof setTimeout>;
  let stopped = false;
  const tick = () => {
    if (stopped) return;
    try { log.info("Deliveries purged", purgeDeliveries(path, days)); } catch (e: any) { log.error("Deliveries purge failed", { error: String(e?.message ?? e) }); }
    timer = setTimeout(tick, intervalSeconds * 1000);
  };
  timer = setTimeout(tick, initialDelay * 1000);
  return () => { stopped = true; clearTimeout(timer); };
}
