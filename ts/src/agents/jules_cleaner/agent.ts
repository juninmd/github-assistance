/** Delete old Jules sessions to keep the account clean. */
import { BaseAgent } from "../base-agent.ts";
import type { AgentOpts } from "../agent-types.ts";

const envInt = (n: string, d: number, min = 1) => { const v = parseInt(process.env[n] ?? "", 10); return Number.isNaN(v) ? d : Math.max(min, v); };

export class JulesCleanerAgent extends BaseAgent {
  constructor(o: AgentOpts) { super("jules_cleaner", { ...o, enforceRepositoryAllowlist: false }); }
  get persona() { return "Jules retention operator"; }
  get mission() { return "Delete Jules sessions older than the retention window."; }

  async run() {
    const maxAgeDays = envInt("JULES_CLEANER_MAX_AGE_DAYS", 3), pageSize = envInt("JULES_CLEANER_PAGE_SIZE", 100), timeout = envInt("JULES_CLEANER_TIMEOUT_SECONDS", 90);
    const cutoff = new Date(Date.now() - maxAgeDays * 86400_000);
    let scanned = 0, deleted = 0, skippedRecent = 0, skippedUnknownAge = 0, failed = 0;
    const failedSessions: string[] = [];
    this.log(`Deleting Jules sessions created before ${cutoff.toISOString()}`);
    for (const s of await this.julesClient.listSessions({ pageSize, timeoutMs: timeout * 1000 })) {
      scanned++;
      const id = s.id || s.name, created = s.createTime ? Date.parse(s.createTime) : NaN;
      if (!id || Number.isNaN(created)) { skippedUnknownAge++; continue; }
      if (created >= cutoff.getTime()) { skippedRecent++; continue; }
      try { await this.julesClient.deleteSession(id); deleted++; }
      catch (e: any) { failed++; failedSessions.push(String(id)); this.log(`Failed to delete Jules session ${id}: ${e?.message ?? e}`, "ERROR"); }
    }
    this.log(`Jules cleanup complete: scanned=${scanned} deleted=${deleted} recent=${skippedRecent} failed=${failed}`);
    return { status: failed ? "failed" : "success", retention_days: maxAgeDays, cutoff: cutoff.toISOString(), scanned, deleted, skipped_recent: skippedRecent, skipped_unknown_age: skippedUnknownAge, failed, failed_sessions: failedSessions.slice(0, 20) };
  }
}
