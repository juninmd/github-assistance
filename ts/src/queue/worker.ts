/** Queue worker: claims durable jobs, runs a handler, records outcomes. */
import { getLogger } from "../utils/logger.ts";
import type { Job } from "./schema.ts";
import type { JobStore } from "./store.ts";

const log = getLogger("queue-worker");
export type Outcome = { status?: string; error?: string | null; decision?: string; next_action?: string; sha?: string | null; task_id?: string | null; [k: string]: any };
export type Handler = (job: Job) => Promise<Outcome | void> | Outcome | void;

export class QueueWorker {
  private stopped = false;
  constructor(
    private store: JobStore,
    private handle: Handler,
    private o: { leaseSeconds?: number; backoffSeconds?: number; limit?: number; clock?: () => number } = {},
  ) {}

  stop() { this.stopped = true; }
  private clock() { return (this.o.clock ?? (() => Date.now() / 1000))(); }

  async runOnce(now?: number): Promise<any[]> {
    const out: any[] = [];
    for (let i = 0; i < (this.o.limit ?? 1); i++) {
      if (this.stopped) break;
      const at = now ?? this.clock();
      this.store.recoverStale(at);
      const jobs = this.store.claim(at, 1, this.o.leaseSeconds ?? 300);
      if (!jobs.length) break;
      out.push(await this.process(jobs[0], at));
    }
    return out;
  }

  private async process(job: Job, now: number) {
    let outcome: Outcome;
    try {
      outcome = (await this.handle(job)) ?? {};
    } catch (e: any) {
      log.error("job handler failed", { job: job.id, error: String(e?.message ?? e) });
      outcome = { status: "failed", error: String(e?.message ?? e) };
    }
    let status = outcome.status ?? "failed";
    if (!["succeeded", "failed", "blocked"].includes(status)) {
      log.warning("handler returned unknown status; treating as failed", { job: job.id, status });
      outcome.error = outcome.error || `unknown status: ${status}`;
      status = "failed";
    }
    return this.store.complete(job.id, status, {
      error: outcome.error, decision: outcome.decision, next_action: outcome.next_action,
      sha: outcome.sha, task_id: outcome.task_id, now,
      backoff_seconds: this.o.backoffSeconds ?? 60, lease_token: job.lease_token,
    });
  }

  async runUntilEmpty(now?: number): Promise<number> {
    let n = 0;
    for (;;) {
      const o = await this.runOnce(now);
      if (!o.length) return n;
      n += o.length;
      now = undefined;
      if (this.stopped) return n;
    }
  }

  async run(pollSeconds = 15): Promise<void> {
    while (!this.stopped) {
      await new Promise((r) => setTimeout(r, pollSeconds * 1000));
      if (this.stopped) break;
      try { await this.runOnce(); } catch (e: any) { log.error("worker cycle failed", { error: String(e?.message ?? e) }); }
    }
  }
}

export const makeObserverHandler = (): Handler => () => ({
  status: "succeeded", decision: "observed", next_action: "observe",
});
