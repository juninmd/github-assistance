/** Draft + commit-status gate for critical review findings (best-effort; never throws into the run). */
import type { GithubClient, PR } from "../../github/client.ts";
import { GATE_NAME, LABEL_CRITICAL, blocks, isApproved, type ReviewVerdict } from "./review-verdict.ts";
import { hasLabel, KEEP_DRAFT_LABEL } from "../core/pr-options.ts";

const CRITICAL_COLOR = "b60205";
export const gateEnabled = () => ["1", "true", "yes", "on"].includes((process.env.REVIEW_GATE_ENABLED ?? "true").toLowerCase());
type Log = (m: string, level?: string) => void;
async function bestEffort(action: () => Promise<unknown>, log: Log, what: string) {
  try { await action(); } catch (e) { log(`review gate: ${what} failed: ${e}`, "WARNING"); }
}
export async function applyGate(pr: PR, gh: GithubClient, verdict: ReviewVerdict, enabled: boolean, log: Log, minSeverity = "error"): Promise<void> {
  if (!enabled) return;
  const repo = pr.base.repo.full_name;
  const status = (state: string, description: string) => gh.createStatus(repo, pr.head.sha, { state, context: GATE_NAME, description });
  if (blocks(verdict, minSeverity) && !isApproved(verdict)) {
    if (!pr.draft) await bestEffort(() => gh.setDraft(pr, true), log, "convert_to_draft");
    await bestEffort(async () => {
      const existing = new Set((await gh.getLabels(repo)).map((l: any) => l.name.toLowerCase()));
      if (!existing.has(LABEL_CRITICAL.toLowerCase())) await gh.createLabel(repo, { name: LABEL_CRITICAL, color: CRITICAL_COLOR });
      await gh.addLabelToPr(pr, LABEL_CRITICAL);
    }, log, "label");
    await bestEffort(() => status("failure", "Achados críticos — corrija antes do merge."), log, "status");
  } else if (isApproved(verdict)) {
    await bestEffort(() => status("success", "Revisão aprovada."), log, "status");
    // `keep-draft` (builder PRs): the owner alone decides when it leaves draft.
    if (pr.draft && !hasLabel(pr, KEEP_DRAFT_LABEL)) await bestEffort(() => gh.setDraft(pr, false), log, "mark_ready");
    await bestEffort(() => gh.removeLabel(pr, LABEL_CRITICAL), log, "unlabel");
  }
}
