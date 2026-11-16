/** Seed selection: pick a domain/archetype/twist while avoiding saturated areas. */
import { ARCHETYPES, DOMAINS, TWISTS } from "./catalog.ts";
import type { Portfolio } from "./portfolio.ts";

export type Seed = { domain: string; angles: string[]; archetype: string; archetypeDesc: string; stacks: string[]; twist: string };
/** Injectable randomness (tests pass a seeded one). */
export type Rng = { random(): number };
export const defaultRng: Rng = { random: Math.random };

const pick = <T>(rng: Rng, xs: T[]): T => xs[Math.floor(rng.random() * xs.length)];
function sample<T>(rng: Rng, xs: T[], k: number): T[] {
  const a = [...xs];
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rng.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a.slice(0, k);
}
function weighted<T>(rng: Rng, xs: T[], weights: number[]): T {
  let r = rng.random() * weights.reduce((a, b) => a + b, 0);
  for (let i = 0; i < xs.length; i++) { r -= weights[i]; if (r < 0) return xs[i]; }
  return xs[xs.length - 1];
}

/** How many existing repos (name + description) hit each domain's keywords. */
export function domainSaturation(history: string[]): Record<string, number> {
  const corpus = history.map((h) => h.toLowerCase());
  return Object.fromEntries(DOMAINS.map((d) => [d.name, corpus.filter((t) => d.kw.some((k) => t.includes(k))).length]));
}

/** Stable sort: stacks written in a language the owner actually uses come first. */
export function preferStacks(stacks: string[], languages: string[]): string[] {
  const owned = new Set(languages.map((l) => l.toLowerCase()));
  if (owned.has("javascript")) for (const x of ["js", "node", "nodejs"]) owned.add(x);
  const uses = (s: string) => s.toLowerCase().split(/[^a-z0-9]+/).some((t) => owned.has(t));
  return stacks.map((s, i) => ({ s, i, k: uses(s) ? 0 : 1 })).sort((a, b) => a.k - b.k || a.i - b.i).map((x) => x.s);
}

/** Weighted draw: domains already well represented in `history` become unlikely. */
export function pickSeed(history: string[], rng: Rng = defaultRng, portfolio?: Portfolio | null): Seed {
  const sat = domainSaturation(history);
  const domain = weighted(rng, DOMAINS, DOMAINS.map((d) => d.weight / (1 + sat[d.name]) ** 2));
  const arch = pick(rng, ARCHETYPES);
  return { domain: domain.name, angles: sample(rng, domain.angles, Math.min(3, domain.angles.length)), archetype: arch.name, archetypeDesc: arch.desc,
    stacks: preferStacks(arch.stacks, portfolio?.languages ?? []), twist: pick(rng, TWISTS) };
}
