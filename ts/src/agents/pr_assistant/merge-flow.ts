/** Merge step of the PR Assistant: comment veto, autonomy, SHA/diff-pinned approval, branch update, MergePolicy, substitute CI, billing scan, SHA-locked squash. */
import type { GithubClient, PR } from "../../github/client.ts";
import type { PRAssistantAgent, Results } from "./agent.ts";
import * as billing from "./billing-gate.ts";
import * as notify from "./notifications.ts";
import { checkPipelineStatus } from "./pipeline.ts";
import { approvalFor } from "./review-approval.ts";

export async function tryMerge(a: PRAssistantAgent, pr: PR, results: Results, comments: any[], reviewExempt = false): Promise<void> {
  const repo = pr.base.repo.full_name, gh: GithubClient = a.githubClient;
  const autonomy = a.autonomy.forRepository(repo);
  const [should, reason] = await a.evaluateComments(pr, comments);
  // Rejection or evaluator unavailability blocks/waits — never close the PR.
  if (!should) { results.skipped.push({ pr: pr.number, title: pr.title, reason, repository: repo }); return; }
  if (!(autonomy.merge && autonomy.mode === "merge")) { a.recordBlocked(results, pr, repo, `autonomy_mode:${autonomy.mode}`); return; }
  // Last line of defence: whatever path got here, merge only on an explicit APPROVE pinned to this exact head SHA.
  const approvedSha = pr.head.sha;
  if (a.requireReview && !reviewExempt && !(await reviewApproved(a, pr))) { a.recordBlocked(results, pr, repo, "review_not_approved", approvedSha); return; }
  if (a.simulationMode) { a.log(`[SIMULATION] would merge PR #${pr.number} in ${repo}`); results.skipped.push({ pr: pr.number, title: pr.title, reason: "simulation", repository: repo }); return; }
  const ms = pr.mergeable_state;
  if (ms === null || ms === undefined || ms === "unknown") { a.recordBlocked(results, pr, repo, "mergeable_state_unknown"); return; }
  let newSha = "";
  // update-branch 422s on an up-to-date branch, so only call it when GitHub says behind.
  if (ms === "behind") {
    const [ok, msg, sha] = await gh.updatePrBranch(pr);
    if (!ok) { a.recordBlocked(results, pr, repo, `update_branch_failed: ${msg}`); return; }
    newSha = sha;
  }
  try { pr = await gh.getPull(repo, pr.number); } catch (e) { a.recordBlocked(results, pr, repo, `refresh_failed: ${e}`); return; }
  if (!newSha && pr.head.sha !== approvedSha) { a.recordBlocked(results, pr, repo, "sha_changed_after_review", pr.head.sha); return; }
  const expected = newSha || pr.head.sha;
  const status = await checkPipelineStatus(gh, pr);
  const decision = a.mergePolicy.evaluate({ status, expectedSha: expected, currentSha: pr.head.sha, autonomy });
  if (decision.action !== "merge") { a.recordBlocked(results, pr, repo, decision.reasons.join("|"), expected); return; }
  let local = "";
  if (billing.isBillingBlocked(status) || status.no_ci) { // nothing ran the code: the bot's own build/test gate stands in for CI
    const [ok, msg] = await a.localChecks(pr);
    if (!ok) { a.recordBlocked(results, pr, repo, msg, expected); return; }
    local = msg;
  }
  if (billing.isBillingBlocked(status)) {
    const leaks = await billing.scanAddedLines(gh, pr);
    if (leaks.length) { a.recordBlocked(results, pr, repo, `billing_blocked_credential_found: ${leaks.slice(0, 5).map((h) => `${h.file}:${h.line} -> ${h.rule_id}`).join("; ")}`, expected); return; }
    await postBillingDisclaimer(a, pr, status, expected, comments, local);
  }
  const [ok, msg] = await gh.mergePr(pr, "squash", expected);
  if (ok) {
    results.merged.push({ action: "merged", pr: pr.number, title: pr.title, repository: repo, sha: expected });
    if (!a.simulationMode) await notify.notifyMerged(gh, pr, comments);
    await a.telegram.sendPrNotification(pr);
  } else {
    if (!a.simulationMode) await notify.notifyMergeFailed(gh, a.telegram, pr, msg, comments);
    results.skipped.push({ pr: pr.number, title: pr.title, reason: "merge_failed", error: msg, repository: repo });
  }
}
export async function reviewApproved(a: PRAssistantAgent, pr: PR): Promise<boolean> {
  try { return (await approvalFor(a.githubClient, pr, await a.githubClient.getIssueComments(pr.base.repo.full_name, pr.number), a.reviewers)) === "approved"; }
  catch (e) { a.log(`Could not verify review approval on PR #${pr.number}: ${e}`, "WARNING"); return false; }
}
export async function postBillingDisclaimer(a: PRAssistantAgent, pr: PR, status: Record<string, any>, sha: string, comments?: any[], local = "") {
  try {
    const list = comments ?? (await a.githubClient.getIssueComments(pr.base.repo.full_name, pr.number));
    if (billing.hasDisclaimer(list)) return;
    await a.githubClient.commentOnPr(pr, billing.buildDisclaimer((status.billing_checks ?? []).filter((c: any) => typeof c === "string"), sha, local));
  } catch (e) { a.log(`Could not post billing disclaimer on PR #${pr.number}: ${e}`, "WARNING"); }
}

