#!/usr/bin/env bun
export {};
/** Homologation: run the advisory PR review for one PR with NO writes (no comment, label, status or push). */
process.env.REVIEW_DRY_RUN ??= "true";
process.env.REVIEW_AUTOFIX_ENABLED ??= "false";
const { settingsFromEnv } = await import("../src/config/settings.ts");
const { GithubClient } = await import("../src/github/client.ts");
const { getAiClient } = await import("../src/ai/client.ts");
const { runReview } = await import("../src/agents/pr_assistant/review-flow.ts");
const { GATE_NAME, buildReviewComment, isCritical } = await import("../src/agents/pr_assistant/review-verdict.ts");

const ref = process.argv[2];
if (!ref || !ref.includes("#")) { console.log("usage: bun scripts/review-dry-run.ts owner/repo#number"); process.exit(2); }
const i = ref.lastIndexOf("#"), slug = ref.slice(0, i);
const s = await settingsFromEnv(), gh = new GithubClient(s.githubToken);
const pr = await gh.getPull(slug, parseInt(ref.slice(i + 1), 10));
console.log(`PR:   ${slug}#${pr.number} — ${pr.title}`);
let gate: string;
try {
  const p = await gh.get(`/repos/${pr.base.repo.full_name}/branches/${encodeURIComponent(pr.base.ref)}/protection/required_status_checks`);
  const ctx: string[] = [...(p.contexts ?? []), ...(p.checks ?? []).map((c: any) => c.context)];
  gate = ctx.includes(GATE_NAME) ? `ENFORCED (required check: ${GATE_NAME})` : `NOT ENFORCED (branch protection has no '${GATE_NAME}' check)`;
} catch (e: any) { gate = `NOT ENFORCED (${e?.name})`; }
console.log(`gate: ${gate}`);
const ai = getAiClient("litellm", { model: process.env.LLM_REVIEW_MODEL || "cloud/auto", apiKey: s.litellmApiKey, baseUrl: s.litellmApiBase });
const v = await runReview(gh, pr, ai);
if (!v) { console.log("RESULT: review produced no verdict (clone/opencode/LLM failed)"); process.exit(1); }
console.log(`\nverdict: ${v.verdict} | model: ${v.model} | critical: ${isCritical(v)} | fixes_applied: ${v.fixed}\nfindings: ${v.findings.length}`);
for (const f of v.findings) console.log(`  - [${f.severity}] ${f.file}:${f.line} — ${f.issue}`);
console.log("\n---- comment that WOULD be posted (dry-run: nothing written) ----");
console.log(buildReviewComment(v, pr.head?.sha ?? ""));
