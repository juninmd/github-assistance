/** Run a single agent, track metrics, wrap the result in the RunResult contract and save it. */
import type { Settings } from "./config/settings.ts";
import { AgentMetrics } from "./agents/core/metrics.ts";
import { saveResults } from "./agents/core/reporting.ts";
import { createAgent } from "./agents/registry.ts";
import { runAll as batchRunAll } from "./agents/batch-runner.ts";
import { runResultFromAgentDict } from "./results.ts";
import { getLogger, newCorrelationId } from "./utils/logger.ts";

const log = getLogger("run-agent");

export function isFailedResult(r: Record<string, any>): boolean {
  if ("error" in r || r.status === "failed") return true;
  // Blocked PRs (CI pending, observe mode) are routine waits, not a failed run.
  return r._run_result?.status === "failed";
}
export const anyBatchFailure = (r: Record<string, any>) => "error" in r || r.status === "failed" || Object.values(r).some((v) => v && typeof v === "object" && isFailedResult(v as any));

export async function runAgent(name: string, settings: Settings, o: { provider?: string; model?: string; prRef?: string; save?: boolean } = {}): Promise<Record<string, any>> {
  const cid = newCorrelationId();
  log.info("=".repeat(60)); log.info(`Starting agent: ${name}`, { correlation_id: cid });
  const metrics = new AgentMetrics(name), t0 = performance.now();
  let results: Record<string, any> = {};
  try {
    const agent = await createAgent(name, settings, o);
    results = (await agent.run()) ?? {};
    metrics.incrementProcessed(Array.isArray(results) ? results.length : Object.keys(results).length || 1);
    log.info(`Agent ${name} completed in ${((performance.now() - t0) / 1000).toFixed(1)}s`);
  } catch (e: any) {
    metrics.addError(String(e?.message ?? e)); metrics.incrementFailed();
    log.error(`Agent ${name} failed after ${((performance.now() - t0) / 1000).toFixed(1)}s: ${e?.message ?? e}`);
    results = { error: String(e?.message ?? e) };
  }
  const m = metrics.finalize();
  results._metrics ??= m;
  const rr = runResultFromAgentDict(name, results, cid);
  rr.duration_seconds = m.duration_seconds; rr.pr_ref = o.prRef ?? null;
  results._run_result = rr;
  if (o.save !== false) { try { saveResults(name, results); } catch (e: any) { log.warning(`could not save results: ${e?.message ?? e}`); } }
  return results;
}

export const runAll = (s: Settings, o: { provider?: string; model?: string } = {}) => batchRunAll(s, (n, st, x) => runAgent(n, st, x), o);
