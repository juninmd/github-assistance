/** PR code review via the LiteLLM proxy: advisory, posted once per PR; never affects the merge decision. */
import type { GithubClient, PR } from "../../github/client.ts";
import { buildReviewPrompt, collectDiff } from "./pr-diff.ts";
import { enabled } from "./review-flags.ts";
import { minDiffChars, reviewWithSubagents, subagentsEnabled } from "./review-subagents.ts";

export const LLM_REVIEW_MARKER = "<!-- litellm-review -->";
export const llmReviewEnabled = () => enabled("LLM_REVIEW_ENABLED", true);
export const hasExistingLlmReviewComment = (comments: any[]) => comments.some((c) => (c.body ?? "").includes(LLM_REVIEW_MARKER));
/** [success, report]; report is "" when there is nothing to say. */
export async function reviewPrWithLitellm(gh: GithubClient, pr: PR, ai: { generate(p: string): Promise<string> }): Promise<[boolean, string]> {
  const diff = await collectDiff(gh, pr);
  if (!diff.trim()) return [true, ""];
  if (subagentsEnabled() && diff.length >= minDiffChars()) {
    const [ok, report] = await reviewWithSubagents(gh, pr, diff, ai);
    return ok ? [true, report.trim()] : [false, `LiteLLM review failed: ${report}`];
  }
  let report: string;
  try { report = await ai.generate(await buildReviewPrompt(gh, pr, diff)); } catch (e) { return [false, `LiteLLM review failed: ${e}`]; }
  report = (report || "").trim();
  return !report || report.toLowerCase().startsWith("no issues found") ? [true, ""] : [true, report];
}
export const buildLlmReviewComment = (report: string): string => !report ? "" : [LLM_REVIEW_MARKER, "## 🤖 Revisão Automática — LiteLLM\n", report, "\n---",
  "_Revisão consultiva gerada via LiteLLM por `pr_assistant`; não afeta a decisão de merge._"].join("\n");
