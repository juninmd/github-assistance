/** Run a single agent, track duration, and wrap the result in the RunResult contract. */
import type { Settings } from "./config/settings.ts";
import { createAgent } from "./agents/registry.ts";
import { runResultFromAgentDict } from "./results.ts";
import { getLogger, newCorrelationId } from "./utils/logger.ts";

const log = getLogger("run-agent");

export function isFailedResult(r: Record<string, any>): boolean {
  if ("error" in r || r.status === "failed") return true;
  return r._run_result?.status === "failed";
}

export async function runAgent(
  name: string, settings: Settings, o: { provider?: string; model?: string; prRef?: string } = {},
): Promise<Record<string, any>> {
  const cid = newCorrelationId();
  log.info(`Starting agent: ${name}`, { correlation_id: cid });
  const t0 = performance.now();
  let results: Record<string, any> = {};
  try {
    const agent = await createAgent(name, { settings, ...o });
    results = (await agent.run()) ?? {};
    log.info(`Agent ${name} completed in ${((performance.now() - t0) / 1000).toFixed(1)}s`);
  } catch (e: any) {
    log.error(`Agent ${name} failed: ${e?.message ?? e}`);
    results = { error: String(e?.message ?? e) };
  }
  const duration = (performance.now() - t0) / 1000;
  const rr = runResultFromAgentDict(name, results, cid);
  rr.duration_seconds = duration;
  rr.pr_ref = o.prRef ?? null;
  results._run_result = rr;
  results._metrics = { duration_seconds: duration };
  return results;
}
