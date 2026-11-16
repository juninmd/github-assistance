/** Parallel specialist reviewers for the advisory LLM PR review (opt-in: LLM_REVIEW_SUBAGENTS=true). */
import type { GithubClient, PR } from "../../github/client.ts";
import { RULES, advisoriesEnabled, readmeExcerpt } from "./review-advisories.ts";
import { enabled } from "./review-flags.ts";

export const NO_ISSUES = "no issues found";
export const SPECIALISTS: Record<string, string> = {
  "Segurança": "Focus ONLY on security: injection, secrets/credentials, unsafe deserialization, path traversal, missing authz/validation, unsafe subprocess use.",
  "Correção": "Focus ONLY on correctness: logic bugs, off-by-one, None/empty handling, wrong conditions, resource leaks, race conditions, broken error handling, API misuse.",
  "Testes": "Focus ONLY on test gaps: new or changed behaviour in the diff with no test, removed/weakened assertions, tests that cannot fail.",
};
export const ADVISORY_SPECIALIST: [string, string] = ["Stack e docs", "Focus ONLY on outdated stack/libraries and README drift (non-blocking advice). " + RULES];
export const activeSpecialists = (): Record<string, string> => (advisoriesEnabled() ? { ...SPECIALISTS, [ADVISORY_SPECIALIST[0]]: ADVISORY_SPECIALIST[1] } : { ...SPECIALISTS });
export const subagentsEnabled = () => enabled("LLM_REVIEW_SUBAGENTS", false);
export function minDiffChars(): number { const n = parseInt(process.env.LLM_REVIEW_SUBAGENTS_MIN_CHARS || "", 10); return Number.isNaN(n) || !n ? 1500 : n; }
export async function specialistPrompt(gh: GithubClient, pr: PR, diff: string, focus: string): Promise<string> {
  let extra = "";
  if (focus.startsWith("Focus ONLY on outdated")) { const ex = await readmeExcerpt(gh, pr); extra = ex ? `README (head):\n${ex}\n\n` : ""; }
  return "You are a senior engineer on a specialist code-review team.\n" + `${focus}\n` +
    "Review ONLY the diff below. Ignore style nits. Report only concrete, " +
    "evidence-backed problems as a short markdown bullet list, each naming the file. " +
    "If there is nothing to flag, reply exactly: No issues found.\n\n" + `PR title: ${pr.title}\n\n${extra}Diff:\n${diff}`;
}
const bullets = (t: string) => t.split(/\r?\n/).map((l) => l.trim()).filter((l) => /^[-*•]/.test(l));
const norm = (b: string) => b.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
export function mergeFindings(results: Record<string, string>): string {
  const seen = new Set<string>(); const sections: string[] = [];
  for (const [name, raw] of Object.entries(results)) {
    const text = (raw || "").trim();
    if (!text || text.toLowerCase().startsWith(NO_ISSUES)) continue;
    const fresh: string[] = [];
    for (const item of bullets(text).length ? bullets(text) : [text]) { const k = norm(item); if (k && !seen.has(k)) { seen.add(k); fresh.push(item); } }
    if (fresh.length) sections.push(`**${name}**\n` + fresh.join("\n"));
  }
  return sections.join("\n\n");
}
export async function reviewWithSubagents(gh: GithubClient, pr: PR, diff: string, ai: { generate(p: string): Promise<string> }): Promise<[boolean, string]> {
  const answers = await Promise.all(Object.entries(activeSpecialists()).map(async ([name, focus]): Promise<[string, string | null]> => {
    try { return [name, await ai.generate(await specialistPrompt(gh, pr, diff, focus))]; } catch { return [name, null]; }
  }));
  const results = Object.fromEntries(answers.filter(([, t]) => t !== null) as [string, string][]);
  return Object.keys(results).length ? [true, mergeFindings(results)] : [false, "all specialist reviewers failed"];
}
