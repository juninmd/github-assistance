/** Per-agent LLM cost ledger (JSONL, AI_USAGE_LOG). Token figures are estimates. */
import { appendFileSync, mkdirSync, readFileSync } from "node:fs";
import { dirname } from "node:path";

const append = (row: object) => {
  const path = process.env.AI_USAGE_LOG;
  if (!path) return;
  try { mkdirSync(dirname(path), { recursive: true }); appendFileSync(path, JSON.stringify(row) + "\n"); } catch { /* observability must not break agents */ }
};

export function recordRun(m: Record<string, any>): void {
  if (!process.env.AI_USAGE_LOG || !((m.llm_calls ?? 0) + (m.llm_cache_hits ?? 0))) return;
  append({ ts: Math.round(Date.now() / 1000), agent: m.agent_name, calls: m.llm_calls ?? 0, cache_hits: m.llm_cache_hits ?? 0,
    tokens_in: m.llm_tokens_in_est ?? 0, tokens_out: m.llm_tokens_out_est ?? 0, tokens_saved: m.llm_tokens_saved_est ?? 0 });
}

export type Trace = { harness: string; model: string; skills_used: string[]; skills_available: string[]; tokens_in: number; tokens_out: number; cost: number | null; tools: string[] };
export function recordTrace(t: Trace): void {
  append({ ts: Math.round(Date.now() / 1000), agent: "opencode", harness: t.harness, model: t.model, skills_used: t.skills_used,
    skills_available: t.skills_available.length, tokens_in: t.tokens_in, tokens_out: t.tokens_out, cost: t.cost,
    tokenix: (t.harness ?? "").includes("tokenix"), tokenix_calls: t.tools.filter((x) => x.startsWith("tokenix_")).length, calls: 1 });
}

function rows(path: string, sinceHours?: number): any[] {
  const cutoff = sinceHours ? Date.now() / 1000 - sinceHours * 3600 : 0;
  let lines: string[];
  try { lines = readFileSync(path, "utf8").split("\n"); } catch { return []; }
  const out: any[] = [];
  for (const l of lines) { try { const r = JSON.parse(l); if ((r.ts ?? 0) >= cutoff) out.push(r); } catch { /* skip */ } }
  return out;
}

export function summarize(path: string, sinceHours?: number) {
  const t = new Map<string, any>();
  for (const r of rows(path, sinceHours)) {
    const k = r.agent || "?";
    const g = t.get(k) ?? { agent: k, runs: 0, calls: 0, cache_hits: 0, tokens: 0, tokens_saved: 0 };
    g.runs++; g.calls += r.calls ?? 0; g.cache_hits += r.cache_hits ?? 0; g.tokens += (r.tokens_in ?? 0) + (r.tokens_out ?? 0); g.tokens_saved += r.tokens_saved ?? 0;
    t.set(k, g);
  }
  return [...t.values()].sort((a, b) => b.tokens - a.tokens);
}

export function summarizeSkills(path: string, sinceHours?: number) {
  const c = new Map<string, any>();
  for (const r of rows(path, sinceHours).filter((r) => "harness" in r))
    for (const skill of r.skills_used?.length ? r.skills_used : ["(nenhuma)"]) {
      const k = `${r.harness || "?"}\u0000${skill}`;
      const g = c.get(k) ?? { harness: r.harness || "?", skill, runs: 0 };
      g.runs++; c.set(k, g);
    }
  return [...c.values()].sort((a, b) => b.runs - a.runs);
}

export function summarizeTokenix(path: string, sinceHours?: number) {
  const g: Record<string, { runs: number; tokens: number; tokenix_calls: number }> = { with: { runs: 0, tokens: 0, tokenix_calls: 0 }, without: { runs: 0, tokens: 0, tokenix_calls: 0 } };
  for (const r of rows(path, sinceHours).filter((r) => "harness" in r)) {
    const x = g[r.tokenix ? "with" : "without"];
    x.runs++; x.tokens += (r.tokens_in ?? 0) + (r.tokens_out ?? 0); x.tokenix_calls += r.tokenix_calls ?? 0;
  }
  return Object.fromEntries(Object.entries(g).map(([k, v]) => [k, { ...v, mean_tokens: v.runs ? Math.round((v.tokens / v.runs) * 10) / 10 : 0 }]));
}
