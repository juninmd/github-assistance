/** LLM usage accounting + response cache (LRU, optionally sqlite-backed via AI_CACHE_PATH). */
import { createHash } from "node:crypto";
import { Database } from "bun:sqlite";

export const CHARS_PER_TOKEN = 4;
export class TokenBudgetExceeded extends Error {}

export const tokenBudget = (): number => Math.max(0, parseInt(process.env.AI_TOKEN_BUDGET ?? "0", 10) || 0);
export const estimateTokens = (t: string) => (t ? Math.ceil(t.length / CHARS_PER_TOKEN) : 0);
export const cacheEnabled = () => !["0", "false", "off", "no"].includes((process.env.AI_CACHE ?? "1").toLowerCase());

export class LLMUsage {
  private cache = new Map<string, string>();
  calls = 0; cacheHits = 0; errors = 0; tokensIn = 0; tokensOut = 0; tokensSaved = 0; seconds = 0;
  byMethod: Record<string, number> = {};
  constructor(public maxEntries = 256, public dbPath: string | null = null) {}

  resetCounters() { this.calls = this.cacheHits = this.errors = this.tokensIn = this.tokensOut = this.tokensSaved = 0; this.seconds = 0; this.byMethod = {}; }
  clearCache() { this.cache.clear(); }

  private db(): Database | null {
    if (!this.dbPath) return null;
    const d = new Database(this.dbPath, { create: true });
    d.exec("CREATE TABLE IF NOT EXISTS ai_cache (k TEXT PRIMARY KEY, v TEXT)");
    return d;
  }
  get(key: string): string | null {
    const hit = this.cache.get(key);
    if (hit !== undefined) { this.cache.delete(key); this.cache.set(key, hit); return hit; }
    try {
      const d = this.db();
      if (!d) return null;
      try { return (d.query("SELECT v FROM ai_cache WHERE k=?").get(key) as any)?.v ?? null; } finally { d.close(); }
    } catch { return null; }
  }
  put(key: string, value: string) {
    this.cache.delete(key); this.cache.set(key, value);
    while (this.cache.size > this.maxEntries) this.cache.delete(this.cache.keys().next().value as string);
    try { const d = this.db(); if (d) try { d.query("INSERT OR REPLACE INTO ai_cache VALUES (?,?)").run(key, value); } finally { d.close(); } } catch { /* cache is best-effort */ }
  }
  record(method: string, tin: number, tout: number, seconds: number, o: { hit?: boolean; error?: boolean } = {}) {
    this.calls += o.hit ? 0 : 1;
    this.byMethod[method] = (this.byMethod[method] ?? 0) + 1;
    if (o.hit) { this.cacheHits++; this.tokensSaved += tin + tout; } else { this.tokensIn += tin; this.tokensOut += tout; this.seconds += seconds; }
    if (o.error) this.errors++;
  }
  snapshot() {
    const total = this.calls + this.cacheHits;
    return {
      llm_calls: this.calls, llm_cache_hits: this.cacheHits,
      llm_cache_hit_rate: total ? Math.round((this.cacheHits / total) * 1000) / 10 : 0,
      llm_errors: this.errors, llm_tokens_in_est: this.tokensIn, llm_tokens_out_est: this.tokensOut,
      llm_tokens_saved_est: this.tokensSaved, llm_seconds: Math.round(this.seconds * 100) / 100,
      llm_calls_by_method: { ...this.byMethod },
    };
  }
  delta(start: ReturnType<LLMUsage["snapshot"]>) { return LLMUsage.deltaOf(this.snapshot(), start); }
  static deltaOf(now: Record<string, any>, start: Record<string, any>) {
    const out: Record<string, any> = {};
    for (const [k, v] of Object.entries(now)) {
      if (k === "llm_calls_by_method") {
        out[k] = Object.fromEntries(Object.entries<number>(v).map(([m, n]) => [m, n - (start[k]?.[m] ?? 0)]).filter(([, n]) => n));
      } else if (k !== "llm_cache_hit_rate") out[k] = typeof v === "number" ? Math.round((v - (start[k] ?? 0)) * 100) / 100 : v;
    }
    const total = out.llm_calls + out.llm_cache_hits;
    out.llm_cache_hit_rate = total ? Math.round((out.llm_cache_hits / total) * 1000) / 10 : 0;
    return out;
  }
}

export const usage = new LLMUsage(parseInt(process.env.AI_CACHE_MAX_ENTRIES ?? "256", 10) || 256, process.env.AI_CACHE_PATH || null);
const CACHEABLE = new Set(["generate", "generate_pr_comment"]);

/** Wrap an LLM call with accounting, budget check and cache for pure text calls. */
export async function instrument(method: string, client: { constructor: { name: string }; model?: string }, args: string[], fn: () => Promise<string>, u: LLMUsage = usage): Promise<string> {
  const textIn = args.join("");
  const tin = estimateTokens(textIn);
  let key: string | null = null;
  if (CACHEABLE.has(method) && cacheEnabled()) {
    key = createHash("sha256").update(`${client.constructor.name}|${client.model ?? ""}|${method}|${textIn}`).digest("hex");
    const hit = u.get(key);
    if (hit !== null) { u.record(method, tin, estimateTokens(hit), 0, { hit: true }); return hit; }
  }
  const budget = tokenBudget();
  if (budget && u.tokensIn + u.tokensOut + tin > budget) throw new TokenBudgetExceeded(`AI_TOKEN_BUDGET=${budget} exhausted`);
  const t0 = performance.now();
  let out: string;
  try { out = await fn(); } catch (e) { u.record(method, tin, 0, (performance.now() - t0) / 1000, { error: true }); throw e; }
  u.record(method, tin, estimateTokens(out ?? ""), (performance.now() - t0) / 1000);
  if (key && out?.trim()) u.put(key, out);
  return out;
}
