/** PR reviews (opencode, LiteLLM as gateway) for the PR Assistant. The SHA-pinned verdict comment is what the merge gate reads. */
import type { RepoAutonomy } from "../../config/autonomy.ts";
import { allowsWrite } from "../../config/autonomy.ts";
import type { GithubClient, PR } from "../../github/client.ts";
import { Semaphore } from "../../utils/semaphore.ts";
import { approvalFor } from "./review-approval.ts";
import { prFingerprint } from "./diff-fingerprint.ts";
import { isDependencyBot } from "./dependency-lane.ts";
import { ReviewInfraError } from "./review-errors.ts";
import { notifyReview } from "./notifications.ts";
import { decideWaiver, hasWaiver, pendingComment, pendingSince, waiverComment, waiverEnabled } from "./review-waiver.ts";
import * as flags from "./review-flags.ts";
import { autofixEnabled, runReview } from "./review-flow.ts";
import { shouldAutofix } from "./review-authors.ts";
import { withPrLock } from "./pr-lock.ts";
import type { ReviewVerdict as Verdict } from "./review-verdict.ts";
import { applyGate, gateEnabled } from "./review-gate.ts";
import { inlineComments, prLines } from "./review-lines.ts";
import { LABEL_COLORS, blocks, isApproved, buildReviewComment, verdictLabel, type ReviewVerdict } from "./review-verdict.ts";

const MAX_FAILURES = 3;
type Log = (m: string, level?: string) => void;
/** approved: explicit APPROVE for the current SHA/diff; blocked: REQUEST_CHANGES; deferred: could not run now (infra error, budget, or model outage still young); waived: models failed long enough on a small diff, notice posted, merge may go on; unreviewed: no verdict; skipped: dependency bots take the dependency lane. */
export type ReviewOutcome = "approved" | "blocked" | "deferred" | "unreviewed" | "skipped" | "waived";

export class ReviewRunner {
  active: boolean;
  private slot = new Semaphore(1); // one opencode (Node) process at a time: 5 in parallel OOMKilled the pod
  private started = 0;
  private brokenByFailures = false;
  private failures = 0; // consecutive model failures; infra errors (token, clone) never count
  private waived = 0;
  constructor(private o: { gh: GithubClient; log: Log; forRepository: (r: string) => RepoAutonomy; active: boolean; budget: number; waitSeconds: number; reviewers?: string[];
    telegram?: { sendMessage(t: string, m?: string): Promise<boolean> }; review?: (gh: GithubClient, pr: PR) => Promise<Verdict | null> }) {
    this.active = o.active;
  }

  /** opencode+skills review. Never throws, never affects merge. */
  async runOpencodeReview(pr: PR, comments?: any[], o: { force?: boolean } = {}): Promise<ReviewOutcome> {
    const { gh, log } = this.o;
    if (isDependencyBot(pr.user?.login)) return "skipped";
    if (!this.active && !this.brokenByFailures) return "unreviewed";
    let existing: any[];
    try { existing = comments ?? (await gh.getIssueComments(pr.base.repo.full_name, pr.number)); } catch { return "unreviewed"; }
    // The verdict is pinned to the head SHA: a new push has no review yet and is reviewed again.
    // `/review` from the owner forces a fresh verdict even when one exists for this SHA.
    const known = o.force ? "missing" : await approvalFor(gh, pr, existing, this.o.reviewers ?? []);
    if (known !== "missing") return known === "approved" ? "approved" : "blocked";
    if (this.brokenByFailures) return this.waive(pr, existing, "modelos indisponíveis nesta rodada");
    if (!(await this.acquireSlot(pr))) return "deferred";
    try {
      const review = () => (this.o.review ?? runReview)(gh, pr);
      // Autofix pushes to the branch: hold the per-PR lease so it never races the conflict resolver or pipeline fixer.
      const locked = autofixEnabled() && shouldAutofix(pr.user?.login ?? "");
      const got = locked ? await withPrLock(gh, pr, async () => ({ v: await review() })) : { v: await review() };
      if (got === null) { log(`review of PR #${pr.number} deferred: another agent holds the PR lease`); return "deferred"; }
      const verdict = got.v;
      if (!verdict) return this.failed(pr, "no verdict", existing);
      this.failures = 0;
      // A pushed autofix changed the diff: pin to its commit only. Otherwise also pin to the diff fingerprint.
      const fp = verdict.fixed ? "" : await this.pinnedFingerprint(pr);
      const comment = buildReviewComment(verdict, (verdict.fixed && verdict.commit) || pr.head?.sha || "", fp);
      if (flags.reviewDryRun()) { log(`[DRY-RUN] opencode review for PR #${pr.number}:\n${comment}`); return "unreviewed"; }
      if (comment) await gh.commentOnPr(pr, comment);
      await this.postInline(pr, verdict);
      if (this.o.telegram) await notifyReview(this.o.telegram, pr, verdict);
      await this.applyLabel(pr, verdictLabel(verdict));
      await applyGate(pr, gh, verdict, this.gateOn(pr), log, flags.gateMinSeverity());
      log(`Reviewed PR #${pr.number}: ${verdict.verdict} (${verdictLabel(verdict)})${verdict.fixed ? " · correções enviadas" : ""}${blocks(verdict, flags.gateMinSeverity()) ? " · gate crítico" : ""}`);
      return isApproved(verdict) ? "approved" : "blocked";
    } catch (e) {
      if (e instanceof ReviewInfraError) { log(`review of PR #${pr.number} deferred (infra): ${e.message}`, "ERROR"); return "deferred"; }
      return this.failed(pr, String(e), existing);
    }
    finally { this.slot.release(); }
  }
  /** Fingerprint of the reviewed head only: if the PR moved during the review (before or after reading the files), none. */
  private async pinnedFingerprint(pr: PR): Promise<string> {
    const head = async () => { try { return (await this.o.gh.getPull(pr.base.repo.full_name, pr.number)).head?.sha; } catch { return null; } };
    if ((await head()) !== pr.head?.sha) return "";
    const fp = await prFingerprint(this.o.gh, pr);
    return fp && (await head()) === pr.head?.sha ? fp : "";
  }
  private failed(pr: PR, why: string, existing: any[]): Promise<ReviewOutcome> {
    const off = ++this.failures >= MAX_FAILURES;
    if (off) { this.active = false; this.brokenByFailures = true; }
    this.o.log(`opencode review unavailable for PR #${pr.number} (${why}); ${off ? `disabled for this run after ${this.failures} failures` : waiverEnabled() ? "waiver tiers apply" : "retried next run"}`, "WARNING");
    return this.waive(pr, existing, why);
  }
  /** Review impossible: pending notice first, waiver only after the outage persisted, on a small diff, under the run cap. */
  private async waive(pr: PR, existing: any[], why: string): Promise<ReviewOutcome> {
    if (!waiverEnabled()) return "unreviewed";
    const sha = pr.head?.sha ?? "";
    let list = existing;
    try { if (!list.length) list = await this.o.gh.getIssueComments(pr.base.repo.full_name, pr.number); }
    catch (e) { this.o.log(`Could not read comments for waiver on PR #${pr.number}: ${e}`, "WARNING"); return "unreviewed"; }
    const step = decideWaiver(pr, list, this.waived, Date.now(), this.o.reviewers ?? []);
    if (step === "too_large" || step === "cap") { this.o.log(`review waiver refused for PR #${pr.number} (${step})`, "WARNING"); return "unreviewed"; }
    if (step === "wait") return "deferred";
    if (flags.reviewDryRun()) { this.o.log(`[DRY-RUN] review ${step} for PR #${pr.number}: ${why}`); return step === "waive" ? "waived" : "deferred"; }
    try {
      if (step === "pending") { if (pendingSince(list, sha, this.o.reviewers ?? []) === null) await this.o.gh.commentOnPr(pr, pendingComment(sha, why)); return "deferred"; }
      if (!hasWaiver(list, sha, this.o.reviewers ?? [])) { await this.o.gh.commentOnPr(pr, waiverComment(sha, why)); this.waived++; }
    } catch (e) { this.o.log(`Could not post review-waiver notice on PR #${pr.number}: ${e}`, "WARNING"); return "unreviewed"; }
    return "waived";
  }
  private async postInline(pr: PR, verdict: ReviewVerdict) {
    if (!flags.enabled("REVIEW_INLINE_ENABLED", true)) return;
    try {
      const serious = verdict.findings.filter((f) => ["warn", "warning", "error"].includes(f.severity || ""));
      const { visible, source } = await prLines(this.o.gh, pr);
      const comments = inlineComments(serious, visible, source);
      if (comments.length) await this.o.gh.createReview(pr, { body: "", event: "COMMENT", comments, commit_id: pr.head.sha });
    } catch (e) { this.o.log(`Inline review comments skipped for PR #${pr.number}: ${e}`, "WARNING"); }
  }
  /** Take the single opencode slot if this run's review budget still allows it. */
  async acquireSlot(pr: PR): Promise<boolean> {
    const { log, waitSeconds, budget } = this.o;
    if (!(await this.slot.acquire(waitSeconds * 1000))) { log(`review slot busy after ${waitSeconds}s; skipping PR #${pr.number} (retried next run)`, "WARNING"); return false; }
    if (this.started >= budget) { this.slot.release(); log(`review budget ${budget}/run reached; skipping PR #${pr.number}`, "WARNING"); return false; }
    this.started++;
    return true;
  }
  gateOn(pr: PR): boolean { return gateEnabled() && allowsWrite(this.o.forRepository(pr.base.repo.full_name)); }
  async applyLabel(pr: PR, label: string): Promise<void> {
    try {
      const repo = pr.base.repo.full_name;
      const existing = new Set((await this.o.gh.getLabels(repo)).map((l: any) => l.name.toLowerCase()));
      if (!existing.has(label.toLowerCase())) await this.o.gh.createLabel(repo, { name: label, color: LABEL_COLORS[label] ?? "ededed" });
      await this.o.gh.addLabelToPr(pr, label);
      // A new push gets a new verdict: drop the stale ones (the gate re-adds review/critical when it applies).
      for (const old of Object.keys(LABEL_COLORS).filter((l) => l !== label)) await this.o.gh.removeLabel(pr, old);
    } catch (e) { this.o.log(`Could not apply review label '${label}' on PR #${pr.number}: ${e}`, "WARNING"); }
  }
}
