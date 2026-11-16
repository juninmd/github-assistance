/** Run enabled agents in dependency-respecting parallel batches; dependents run only after real success. */
import { AGENT_CATALOG } from "./catalog.ts";
import { createDefaultOrchestrator, type AgentOrchestrator } from "./orchestration.ts";
import { AGENTS_WITH_AI } from "./registry.ts";
import type { Settings } from "../config/settings.ts";
import { getLogger } from "../utils/logger.ts";

const log = getLogger("batch-runner");
const MAX_PARALLEL = 10;
const isFailure = (r: Record<string, any>) => !!r.error || ["failed", "blocked"].includes(r.status);
const blockedDeps = (o: AgentOrchestrator, a: string, ok: Set<string>) => (o.deps.get(a) ?? []).filter((d) => !ok.has(d));

export type RunOne = (name: string, s: Settings, o: { provider?: string; model?: string }) => Promise<Record<string, any>>;

export async function runAll(s: Settings, runOne: RunOne, o: { provider?: string; model?: string } = {}): Promise<Record<string, any>> {
  const enabled = AGENT_CATALOG.filter((a) => a.inBatch && (a.toggleEnv ? s.enabled[a.name] !== false : true) && (!AGENTS_WITH_AI.has(a.name) || s.enableAi)).map((a) => a.name);
  const orch = createDefaultOrchestrator();
  let batches: string[][];
  try { batches = enabled.length ? orch.parallelBatches(enabled) : []; } catch (e: any) { return { error: e.message, status: "failed" }; }
  const results: Record<string, any> = {}, ok = new Set<string>();
  for (const [i, batch] of batches.entries()) {
    console.log(`\n${"=".repeat(60)}\nBatch ${i + 1}/${batches.length}: ${batch.join(", ")}\n${"=".repeat(60)}`);
    const pending: Promise<void>[] = [];
    let running = 0; const queue = [...batch];
    const worker = async () => {
      for (let name = queue.shift(); name; name = queue.shift()) {
        const missing = blockedDeps(orch, name, ok);
        if (missing.length) { results[name] = { status: "blocked", error: `dependency failed: ${missing.join(", ")}` }; log.error(`Agent ${name} blocked by failed dependency ${JSON.stringify(missing)}`); continue; }
        let r: Record<string, any>;
        try { r = await runOne(name, s, o); } catch { r = { error: "agent execution failed" }; log.error(`Agent ${name} failed`); }
        results[name] = r;
        if (!isFailure(r)) ok.add(name);
      }
    };
    for (let w = 0; w < Math.min(batch.length, MAX_PARALLEL); w++) pending.push(worker());
    await Promise.all(pending);
    void running;
  }
  return results;
}
