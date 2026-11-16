/**
 * Centralized, non-bypassable merge policy: the current SHA's checks must be conclusively green, required evidence must exist,
 * no check may be failed/pending/cancelled/unknown, and the validated head SHA must still match at merge time.
 * A repository with no CI at all may merge without evidence (labelled `sem-ci`).
 */
import { allowsMerge, type RepoAutonomy } from "../../config/autonomy.ts";

type R = Record<string, any>;
export const TRANSIENT_REASONS = ["checks_pending", "checks_unknown", "no_evidence", "ai_unavailable"];
export type MergeDecision = { action: "merge" | "wait" | "blocked"; reasons: string[] };
export const decisionBlocks = (d: MergeDecision, reason: string) => d.action === "blocked" && d.reasons.includes(reason);

function missingRequired(status: R, required: string[]): string[] {
  if (!required.length) return [];
  const seen = new Set((status.success_checks ?? []).map((c: R) => c.context));
  return required.filter((n) => !seen.has(n));
}

export class MergePolicy {
  evaluate(o: { status: R; expectedSha?: string | null; currentSha?: string | null; autonomy: RepoAutonomy }): MergeDecision {
    const { status, expectedSha, currentSha, autonomy } = o, reasons: string[] = [], state = status.state;
    if (status.failed_checks?.length) reasons.push("checks_failed");
    else if (status.cancelled_checks?.length) reasons.push("checks_cancelled");
    else if (state === "unknown") reasons.push("checks_unknown");
    else if (state === "pending") reasons.push(autonomy.require_evidence && !status.has_evidence ? "no_evidence" : "checks_pending");
    else if (state !== "success") reasons.push("checks_failed");
    if (autonomy.require_evidence && !status.has_evidence && !status.no_ci && !reasons.includes("no_evidence")) reasons.push("no_evidence");
    const missing = missingRequired(status, autonomy.required_checks);
    if (missing.length) reasons.push(`missing_checks:${[...missing].sort().join(",")}`);
    if (expectedSha && currentSha && currentSha !== expectedSha) reasons.push("sha_changed");
    if (!allowsMerge(autonomy)) reasons.push(`autonomy_mode:${autonomy.mode}`);
    if (!reasons.length) return { action: "merge", reasons };
    return { action: reasons.some((r) => TRANSIENT_REASONS.includes(r)) ? "wait" : "blocked", reasons };
  }
}
/** Reason string when the repo policy forbids autonomous merge. */
export const autonomyBlocksMerge = (a: RepoAutonomy): string | null => (allowsMerge(a) ? null : `autonomy_mode:${a.mode}`);
