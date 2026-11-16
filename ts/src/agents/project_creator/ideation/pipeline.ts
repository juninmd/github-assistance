/** Ideation pipeline: seed -> diverge -> critique -> specify -> quality gate. */
import type { Portfolio } from "./portfolio.ts";
import { critiquePrompt, divergePrompt, queriesPrompt, specifyPrompt } from "./prompts.ts";
import { formatResearch, type MarketResearcher } from "./research.ts";
import { defaultRng, pickSeed, type Rng, type Seed } from "./seed.ts";

type R = Record<string, any>;
const CRITERIA = ["novelty", "utility", "fit", "feasibility", "distinctiveness"];
const MIN_TOTAL = 19, MIN_CORE = 3, MIN_FIT = 4; // out of 25; novelty+utility >= 3 each; the owner must plausibly use it himself
const BANNED = new Set(["expense", "expenses", "budget", "finance", "finances", "financial", "money", "wallet", "todo", "weather"]);
const FILLER = new Set(["smart", "ai", "app", "tool", "tools", "manager", "tracker", "helper", "assistant", "dashboard", "my", "pro", "hub", "simple", "easy", "super"]);

export function parseJson(text?: string | null): R | null {
  const m = /\{[\s\S]*\}/.exec(text ?? "");
  if (!m) return null;
  try { const d = JSON.parse(m[0]); return d && typeof d === "object" && !Array.isArray(d) ? d : null; } catch { return null; }
}
const tokens = (n: string) => new Set(n.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean));

export function nameProblem(name: string, existing: string[], allowFinance: boolean): string | null {
  const t = tokens(name);
  if (!t.size || [...t].every((x) => FILLER.has(x))) return "name is generic";
  if (!allowFinance && [...t].some((x) => BANNED.has(x))) return "name uses a banned generic theme";
  for (const other of existing) {
    const o = tokens(other);
    if (!o.size) continue;
    const inter = [...t].filter((x) => o.has(x)).length, union = new Set([...t, ...o]).size;
    if (inter / union >= 0.6) return `name too similar to existing repo ${other}`;
  }
  return null;
}

function competitiveBlock(spec: R): string {
  const rivals = (spec.competitors ?? []).filter((c: any) => c && typeof c === "object").map((c: R) => `- [${c.name}](${c.url}): strengths — ${c.strengths}; gaps — ${c.gaps}`).join("\n");
  const borrowed = (spec.external_features ?? []).map((f: string) => `- ${f}`).join("\n");
  if (!rivals && !borrowed) return "";
  return `### Competitive landscape\n${rivals || "n/a"}\n\n### Features borrowed from the market\n${borrowed || "n/a"}\n\nTagline: ${spec.tagline ?? ""}\n\n`;
}

/** Render the structured spec as the implementation brief handed to Jules. */
export function renderPrompt(spec: R): string {
  const features = spec.features.map((f: R, i: number) => `${i + 1}. **${f.name}** — ${f.description}\n   - Acceptance: ${f.acceptance}`).join("\n");
  return `### Problem\n${spec.problem ?? ""}\n\n### Target user\n${spec.target_user ?? ""}\n\n### Features (all required for v1)\n${features}\n\n${competitiveBlock(spec)}` +
    `### Architecture\n${spec.architecture ?? ""}\n\n### Interfaces\n${spec.interfaces ?? ""}\n\n### Fixtures & demo\n${spec.fixtures ?? ""}\n\n### Test plan (write these tests)\n${spec.test_plan ?? ""}\n\n` +
    "Build everything on `master`, run the tests and linters until green, then open a PR.";
}

export class IdeationPipeline {
  constructor(private generate: (p: string) => Promise<string>, private log: (m: string, level?: string) => void,
    private o: { rng?: Rng; candidates?: number; attempts?: number; researcher?: MarketResearcher | null; owner?: string } = {}) {}
  private get n() { return this.o.candidates ?? 5; }

  async run(history: string[], existing: string[], portfolio?: Portfolio | null): Promise<R | null> {
    for (let attempt = 1; attempt <= (this.o.attempts ?? 3); attempt++) {
      const seed = pickSeed(history, this.o.rng ?? defaultRng, portfolio);
      this.log(`Ideation attempt ${attempt}: ${seed.domain} / ${seed.archetype}`);
      const cand = await this.select(seed, history, existing, portfolio);
      if (!cand) continue;
      const spec = await this.specify(cand, seed, existing);
      if (spec) return spec;
    }
    return null;
  }

  private async ask(prompt: string): Promise<R | null> {
    try { return parseJson(await this.generate(prompt)); } catch (e: any) { this.log(`AI call failed during ideation: ${e?.message ?? e}`, "ERROR"); return null; }
  }

  private async select(seed: Seed, history: string[], existing: string[], portfolio?: Portfolio | null): Promise<R | null> {
    const allowFinance = seed.domain.startsWith("finance");
    const raw = (await this.ask(divergePrompt(seed, history, this.n, portfolio)))?.candidates;
    const pool = (Array.isArray(raw) ? raw : []).filter((c: any) => c && typeof c === "object" && c.repository_name && !nameProblem(c.repository_name, existing, allowFinance));
    if (!pool.length) { this.log("No viable candidates after name filtering", "WARNING"); return null; }
    const scores = (await this.ask(critiquePrompt(pool, history, portfolio)))?.scores ?? [];
    let best: R | null = null, bestTotal = 0;
    for (const s of Array.isArray(scores) ? scores : []) {
      try {
        const idx = parseInt(s.index, 10), vals = CRITERIA.map((c) => Math.min(5, Math.max(1, parseInt(s[c], 10)))), total = vals.reduce((a, b) => a + b, 0);
        if (vals.some(Number.isNaN) || Number.isNaN(idx)) continue;
        if (idx >= 0 && idx < pool.length && total >= MIN_TOTAL && Math.min(vals[0], vals[1]) >= MIN_CORE && vals[2] >= MIN_FIT && total > bestTotal) { best = pool[idx]; bestTotal = total; }
      } catch { continue; }
    }
    if (!best) this.log("No candidate passed the critique threshold", "WARNING");
    return best;
  }

  private async research(candidate: R): Promise<string> {
    if (!this.o.researcher) return "none found";
    const queries = (await this.ask(queriesPrompt(candidate)))?.queries ?? [];
    const found = await this.o.researcher.research(Array.isArray(queries) ? queries : [], this.o.owner ?? "");
    this.log(`Research: ${found.competitors.length} competitors, ${found.web.length} web hits`);
    return formatResearch(found);
  }

  private async specify(candidate: R, seed: Seed, existing: string[]): Promise<R | null> {
    const spec = await this.ask(specifyPrompt(candidate, seed, seed.stacks[0], await this.research(candidate)));
    if (!spec) return null;
    const { features, roadmap_features: roadmap } = spec;
    const valid = Array.isArray(features) && features.length >= 4 && features.every((f: any) => f && typeof f === "object") && Array.isArray(roadmap) && roadmap.length >= 8 &&
      String(spec.idea_description ?? "").length >= 80 && spec.repository_name && spec.tech_stack && !nameProblem(spec.repository_name, existing, seed.domain.startsWith("finance"));
    if (!valid) { this.log("Spec failed quality gate", "WARNING"); return null; }
    spec.jules_prompt = renderPrompt(spec);
    return spec;
  }
}
