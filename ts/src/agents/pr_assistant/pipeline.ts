/**
 * Pipeline status evaluation for the current PR head SHA. Failing, pending, unknown, cancelled and absent evidence never
 * count as success; no check-name exemption. GitHub Actions billing refusals (job never started) count as passed.
 */
import { buildOriginMetadata } from "../core/utils.ts";
import type { GithubClient, PR } from "../../github/client.ts";
import { GATE_NAME } from "./review-verdict.ts";

type R = Record<string, any>;
const COVERAGE_RE = /coverage[^0-9]{0,5}(\d{1,3}(?:\.\d+)?)\s*%/i;
const FAILING = new Set(["failure", "timed_out", "action_required", "startup_failure", "stale"]);
const CANCELLED = new Set(["cancelled"]);
const FAILING_STATES = new Set(["failure", "error"]);
// "neutral" and "skipped" mean "not applicable" and count as success; only runs that did not complete are pending.
const BILLING_RE = /account payments have failed|spending limit needs to be increased|exceeded.{0,15}(spending|usage) limit/i;
const ADVISORY_RE = /\b(release[\s_-]?drafter|autolabel)\b/i;
export const NO_CI_LABEL = "sem-ci", NO_CI_LABEL_COLOR = "fbca04";

const isBillingFailure = (t?: string | null) => !!t && BILLING_RE.test(t);
const isAdvisoryCheck = (n?: string) => ADVISORY_RE.test(n ?? "");

class Buckets {
  failed: R[] = []; pending: string[] = []; cancelled: R[] = []; success: string[] = []; coverage: R[] = []; billing: string[] = []; advisory: string[] = []; total = 0;
  successCheck(name: string) { this.success.push(name); this.total++; }
  fail(name: string, description: string, url: string) {
    this.total++;
    if (isBillingFailure(description)) { this.billing.push(name); this.success.push(name); return; }
    if (isAdvisoryCheck(name)) { this.advisory.push(name); this.success.push(name); return; }
    this.failed.push({ context: name, description, url });
  }
  cancel(name: string, description: string) { this.cancelled.push({ context: name, description, url: "" }); this.total++; }
}

export function extractCoverage(text?: string | null): number | null {
  const m = text ? COVERAGE_RE.exec(text) : null;
  const v = m ? parseFloat(m[1]) : NaN;
  return Number.isNaN(v) ? null : v;
}
const checkRunSummary = (cr: R) => (cr.output && typeof cr.output === "object" ? cr.output.summary : null) || "No details";

function processStatuses(statuses: R[], b: Buckets) {
  for (const s of statuses) {
    if (s.context === GATE_NAME) continue; // our own review gate, enforced via branch protection
    b.total++;
    const desc = s.description || "No description", cov = extractCoverage(desc);
    if (cov !== null) b.coverage.push({ check: s.context, coverage: cov });
    if (FAILING_STATES.has(s.state)) b.fail(s.context, desc, s.target_url || "");
    else if (s.state === "pending") b.pending.push(s.context);
    else b.successCheck(s.context);
  }
}
/** A job GitHub refused to start (billing) carries no summary; the reason lives only in the check-run annotations. */
async function billingAnnotation(gh: GithubClient, repo: string, cr: R): Promise<string | null> {
  if (!FAILING.has(cr.conclusion) || !cr.id || !(cr.output?.annotations_count > 0)) return null;
  try {
    const notes: R[] = await gh.paginate(`/repos/${repo}/check-runs/${cr.id}/annotations`);
    return notes.map((n) => n.message).find(isBillingFailure) ?? null;
  } catch { return null; }
}
async function processCheckRuns(gh: GithubClient, repo: string, runs: R[], b: Buckets) {
  for (const cr of runs) {
    if (cr.name === GATE_NAME) continue;
    let summary = checkRunSummary(cr);
    if (!isBillingFailure(summary)) summary = (await billingAnnotation(gh, repo, cr)) ?? summary;
    const cov = extractCoverage(summary);
    if (cov !== null) b.coverage.push({ check: cr.name, coverage: cov });
    b.total++;
    if (FAILING.has(cr.conclusion)) b.fail(cr.name, summary, cr.html_url || "");
    else if (CANCELLED.has(cr.conclusion)) b.cancel(cr.name, summary);
    else if (cr.status !== "completed") b.pending.push(cr.name);
    else b.successCheck(cr.name);
  }
}

/** Evaluate pipeline evidence for `pr.head.sha`. */
export async function checkPipelineStatus(gh: GithubClient, pr: PR): Promise<R> {
  try {
    const repo = pr.base.repo.full_name, sha = pr.head.sha;
    const b = new Buckets();
    processStatuses((await gh.getCombinedStatus(repo, sha)).statuses ?? [], b);
    await processCheckRuns(gh, repo, await gh.getCheckRuns(repo, sha), b);
    const state = b.failed.length || b.cancelled.length ? "failure" : b.pending.length ? "pending" : "success";
    const out: R = {
      state, failed_checks: b.failed, pending_checks: b.pending, cancelled_checks: b.cancelled, success_checks: b.success.map((context) => ({ context })),
      has_evidence: b.total > 0, no_ci: b.total === 0,
      checks: { total: b.total, success: b.success.length, failed: b.failed.length, pending: b.pending.length, cancelled: b.cancelled.length },
      description: `Pipeline state: ${state}`, billing_checks: b.billing, advisory_checks: b.advisory,
    };
    if (b.coverage.length) out.coverage = b.coverage;
    return out;
  } catch (e: any) {
    return {
      state: "unknown", failed_checks: [], pending_checks: [], cancelled_checks: [], success_checks: [], has_evidence: false, no_ci: false,
      checks: { total: 0, success: 0, failed: 0, pending: 0, cancelled: 0 }, billing_checks: [], description: `Error checking pipeline: ${e?.message ?? e}`,
    };
  }
}

export const hasExistingFailureComment = (comments: R[]) => comments.some((c) => (c.body ?? "").includes("Pipeline Failure Detected"));

export function buildFailureComment(pr: PR, failed: R[]): string {
  const failures = failed.map((c) => `- **${c.context}**: ${c.description}` + (c.url ? ` ([details](${c.url}))` : "")).join("\n");
  return `❌ **Pipeline Failure Detected**\n\nHi @${pr.user?.login ?? "contributor"}, the CI/CD pipeline for this PR has failed.\n\n**Failure Details:**\n${failures}\n\n` +
    `Please review the errors above and push corrections to resolve these issues.\nOnce all checks pass, I'll be able to merge this PR automatically.\n\nThank you! 🙏\n\n${buildOriginMetadata("pr_assistant")}`;
}
