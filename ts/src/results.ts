/** Typed execution-result contract for agents and the durable queue. */
import { randomUUID } from "node:crypto";

export const itemCount = (v: unknown) => (Array.isArray(v) ? v.length : v instanceof Set ? v.size : 0);

export type RunResult = {
  agent: string; task_id: string; repo: string | null; pr_ref: string | null; sha: string | null;
  status: string; items_done: number; items_failed: number; items_skipped: number; items_blocked: number;
  duration_seconds: number; api_calls: number; cost: number | null; attempts: number;
  decision: string | null; next_action: string | null; evidence: Record<string, any>[]; error: string | null;
};

export function runResultFromAgentDict(agent: string, data: Record<string, any>, taskId?: string): RunResult {
  const skipped = data.skipped ?? [], blocked = data.blocked ?? [];
  const failed = data.failed ?? data.pipeline_failures ?? [];
  const done = data.merged ?? data.processed ?? data.resolved ?? [];
  let status = "succeeded";
  if (data.error) status = "failed";
  else if ((Array.isArray(blocked) && blocked.length) || data.pipeline_failures?.length) status = "blocked";
  else if (Array.isArray(failed) && failed.length) status = "failed";
  return {
    agent, task_id: taskId ?? randomUUID().slice(0, 8), repo: data.repository ?? data.repo ?? null,
    pr_ref: data.pr_ref ?? null, sha: data.sha ?? null, status,
    items_done: itemCount(done), items_failed: itemCount(failed), items_skipped: itemCount(skipped), items_blocked: itemCount(blocked),
    duration_seconds: Number(data.duration_seconds || 0), api_calls: Number(data.api_calls || 0),
    cost: data.cost ?? null, attempts: Number(data.attempts || 0), decision: data.decision ?? null,
    next_action: data.next_action ?? null, evidence: Array.isArray(data.evidence) ? data.evidence : [], error: data.error ?? null,
  };
}
