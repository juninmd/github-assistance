/** Prompt builders for each ideation stage. */
import type { Portfolio } from "./portfolio.ts";
import type { Seed } from "./seed.ts";

const OWNER = "a Brazilian senior developer (Antonio Carlos)";
const j = (o: unknown) => JSON.stringify(o, null, 1);

const seedBlock = (s: Seed) => `- Domain: ${s.domain}\n- Niche angles to draw from (mix or go beyond): ${s.angles.join("; ")}\n- Project shape: ${s.archetype} (${s.archetypeDesc})\n- Suggested stacks: ${s.stacks.join(", ")}\n- Hard constraint: ${s.twist}`;

/** What the owner really builds (the bar) and what earlier runs got wrong (the anti-pattern). */
export function portfolioBlock(p?: Portfolio | null): string {
  if (!p || !(p.exemplars.length || p.generated.length)) return "";
  const parts: string[] = [];
  if (p.exemplars.length) parts.push(`Repos the owner built by hand (his taste and quality bar):\n${p.exemplars.map((l) => `- ${l}`).join("\n")}`);
  if (p.languages.length) parts.push(`Languages he actually writes: ${p.languages.join(", ")}`);
  if (p.generated.length) parts.push(`Earlier auto-generated repos he never used (generic back-office/SaaS style, do NOT imitate): ${p.generated.join(", ")}`);
  return "Owner portfolio:\n" + parts.join("\n") + "\n\n";
}

export const divergePrompt = (seed: Seed, history: string[], n: number, p?: Portfolio | null) =>
  `You are a product-minded staff engineer inventing side projects for ${OWNER}.\n\n` +
  `Existing repositories (do NOT duplicate or lightly rename any): ${history.join(", ") || "none"}\n\n${portfolioBlock(p)}Creative brief:\n${seedBlock(seed)}\n\n` +
  `Propose ${n} DISTINCT candidate projects. Rules:\n` +
  "- Start from a friction the owner or a developer like him hits weekly (a concrete moment, not a market segment). Prefer a small sharp tool (one verb, useful within minutes) over a platform.\n" +
  "- It must be usable by the owner himself on his own machine/server/phone from day one: no paying customers, no third-party business accounts, no back-office workflows (contracts, retainers, invoicing, release orchestration, 'autonomous X' platforms).\n" +
  "- Prefer extending or pairing with something he already built (name it in `complements`) over a disconnected idea.\n" +
  "- Forbidden: generic expense/budget/finance trackers, todo apps, habit trackers, weather apps, 'AI assistant' wrappers, dashboards without a unique data source.\n" +
  "- Candidates must differ from each other in problem, user and mechanism.\n- Names are memorable and specific (not 'smart-xyz-manager').\n" +
  "- Scope: a polished, tested v1 buildable by one autonomous coding agent in one session.\n\n" +
  'Reply with JSON only: {"candidates": [{"repository_name": "kebab-case", "title": "...", "friction": "the concrete weekly moment that hurts", "complements": "owner repo it pairs with, or standalone", "problem": "...", "target_user": "...", "core_mechanism": "...", "differentiator": "what exists today and why this is better"}]}';

export const critiquePrompt = (candidates: unknown[], history: string[], p?: Portfolio | null) =>
  "You are a skeptical product reviewer. Score each candidate 1-5 (integers, be harsh; 3 is average, 5 is exceptional) on:\n" +
  "- novelty: not a clone of a popular tool or a tutorial project\n- utility: a real user would adopt it repeatedly\n" +
  "- fit: the owner (see portfolio) would plausibly use it himself within a week; 1 for generic business tooling nobody on his machine needs\n" +
  "- feasibility: a complete tested v1 fits in one session\n" +
  `- distinctiveness: clearly different from the existing repos (${history.join(", ") || "none"})\n\n${portfolioBlock(p)}Candidates:\n${j(candidates)}\n\n` +
  'Reply with JSON only: {"scores": [{"index": 0, "novelty": 1, "utility": 1, "fit": 1, "feasibility": 1, "distinctiveness": 1, "reason": "one sentence"}]}';

export const queriesPrompt = (c: unknown) =>
  `Write 3 short search queries (English, 2-5 words each) a developer would type to find existing tools that already solve this problem, from most specific to broadest.\n\n${j(c)}\n\nReply with JSON only: {"queries": ["...", "...", "..."]}`;

export const specifyPrompt = (c: unknown, seed: Seed, stackHint: string, research = "none found") =>
  "You are a principal engineer writing the build spec an autonomous coding agent will follow.\n\n" +
  `Chosen project:\n${j(c)}\n\nShape: ${seed.archetype}. Preferred stack: ${stackHint}. Constraint: ${seed.twist}.\n\n` +
  `Market research (existing GitHub projects and web hits):\n${research}\n\n` +
  "Study the competitors: name what each does well and where it falls short, then borrow the proven features (adapted, never copied code) and pick a clear differentiator. If a competitor already does exactly this, say so in `overlap_risk`.\n\n" +
  "Write a precise, opinionated spec. Features need testable acceptance criteria; the interface section lists exact commands/endpoints/screens with example I/O; roadmap items are independent, single-PR improvements beyond v1 (new capabilities, not chores).\n\n" +
  "Reply with JSON only:\n" +
  '{"repository_name": "kebab-case", "title": "...", "idea_description": "2-3 sentences: what, for whom, why it matters", "tech_stack": "...", "problem": "...", "target_user": "...", ' +
  '"features": [{"name": "...", "description": "...", "acceptance": "..."}], "architecture": "modules, data flow, key decisions", "interfaces": "exact CLI/API/UI surface with example input and output", ' +
  '"fixtures": "bundled sample data and how the demo runs", "test_plan": "unit, integration and edge cases to cover", "tagline": "one punchy line for the README hero", ' +
  '"competitors": [{"name": "owner/repo", "url": "...", "strengths": "...", "gaps": "..."}], "external_features": ["feature seen in competitors worth adopting, with source"], ' +
  '"overlap_risk": "low|medium|high with one sentence", "roadmap_features": [{"title": "...", "objective": "concrete goal and acceptance criteria"}]}\n' +
  "features: 4-6 items. competitors: up to 5 from the research. roadmap_features: 10-12 independent items, most valuable first, including features borrowed from competitors, integrations, performance, UX polish and docs.";
