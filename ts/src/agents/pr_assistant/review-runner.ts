/** Advisory PR reviews (opencode, LiteLLM as gateway) for the PR Assistant: comment/label/gate only, never affects the merge decision. */
import type { RepoAutonomy } from "../../config/autonomy.ts";
import { allowsWrite } from "../../config/autonomy.ts";
import type { GithubClient, PR } from "../../github/client.ts";
import { Semaphore } from "../../utils/semaphore.ts";
import { approvalState } from "./review-approval.ts";
import { notifyReview } from "./notifications.ts";
import { isJules } from "./review-authors.ts";
import { hasWaiver, waiverComment, waiverEnabled } from "./review-waiver.ts";
import * as flags from "./review-flags.ts";
import { runReview } from "./review-flow.ts";
import { applyGate, gateEnabled } from "./review-gate.ts";
import { inlineComments, prLines } from "./review-lines.ts";
import { LABEL_COLORS, blocks, isApproved, buildReviewComment, verdictLabel, type ReviewVerdict } from "./review-verdict.ts";

const MAX_FAILURES = 3;
const isDependabot = (login?: string | null) => /^(app\/)?dependabot(\[bot\])?$/i.test((login ?? "").trim());
type Log = (m: string, level?: string) => void;
/** approved: explicit APPROVE for the current SHA; blocked: REQUEST_CHANGES; deferred: could not run now (retry next run); waived: every model failed, a notice was posted and the merge may go on; unreviewed: no verdict at all; skipped: dependabot PRs are never reviewed. */
export type ReviewOutcome = "approved" | "blocked" | "deferred" | "unreviewed" | "skipped" | "waived";

export class ReviewRunner {
  active: boolean;
  private slot = new Semaphore(1); // one opencode (Node) process at a time: 5 in parallel OOMKilled the pod
  private started = 0;
  private brokenByFailures = false;
  private failures = 0; // consecutive; one bad PR (clone, timeout) must not switch reviews off for the whole run
  constructor(private o: { gh: GithubClient; log: Log; forRepository: (r: string) => RepoAutonomy; active: boolean; budget: number; waitSeconds: number; reviewers?: string[]; telegram?: { sendMessage(t: string, m?: string): Promise<boolean> } }) {
    this.active = o.active;
  }

  /** opencode+skills review. Never throws, never affects merge. */
  async runOpencodeReview(pr: PR, comments?: any[]): Promise<ReviewOutcome> {
    const { gh, log } = this.o;
    if (isDependabot(pr.user?.login)) return "skipped";
    if (!this.active && !this.brokenByFailures) return "unreviewed";
    let existing: any[];
    try { existing = comments ?? (await gh.getIssueComments(pr.base.repo.full_name, pr.number)); } catch { return "unreviewed"; }
    // The verdict is pinned to the head SHA: a new push has no review yet and is reviewed again.
    const known = approvalState(existing, pr.head?.sha ?? "", this.o.reviewers ?? []);
    if (known !== "missing") return known === "approved" ? "approved" : "blocked";
    if (this.brokenByFailures) return this.waive(pr, existing, "modelos indisponíveis nesta rodada");
    if (!(await this.acquireSlot(pr))) return "deferred";
    try {
      const verdict = await runReview(gh, pr);
      if (!verdict) return this.failed(pr, "no verdict", existing);
      this.failures = 0;
      const jules = isJules(pr.user?.login ?? "");
      const comment = buildReviewComment(verdict, (verdict.fixed && verdict.commit) || pr.head?.sha || "", jules);
      if (flags.reviewDryRun()) { log(`[DRY-RUN] opencode review for PR #${pr.number}:\n${comment}`); return "unreviewed"; }
      if (comment) await gh.commentOnPr(pr, comment);
      await this.postInline(pr, verdict);
      if (this.o.telegram) await notifyReview(this.o.telegram, pr, verdict);
      await this.applyLabel(pr, verdictLabel(verdict));
      await applyGate(pr, gh, verdict, this.gateOn(pr), log, flags.gateMinSeverity());
      log(`Reviewed PR #${pr.number}: ${verdict.verdict} (${verdictLabel(verdict)})${verdict.fixed ? " · correções enviadas" : ""}${blocks(verdict, flags.gateMinSeverity()) ? " · gate crítico" : ""}`);
      return isApproved(verdict) ? "approved" : "blocked";
    } catch (e) { return this.failed(pr, String(e), existing); }
    finally { this.slot.release(); }
  }
  private failed(pr: PR, why: string, existing: any[]): Promise<ReviewOutcome> {
    const off = ++this.failures >= MAX_FAILURES;
    if (off) { this.active = false; this.brokenByFailures = true; }
    this.o.log(`opencode review unavailable for PR #${pr.number} (${why}); ${off ? `disabled for this run after ${this.failures} failures` : waiverEnabled() ? "review waived" : "retried next run"}`, "WARNING");
    return this.waive(pr, existing, why);
  }
  /** Review impossible: warn on the PR and let the merge go on, unless waiving is off. */
  private async waive(pr: PR, existing: any[], why: string): Promise<ReviewOutcome> {
    if (!waiverEnabled()) return "unreviewed";
    const sha = pr.head?.sha ?? "";
    if (flags.reviewDryRun()) { this.o.log(`[DRY-RUN] review waived for PR #${pr.number}: ${why}`); return "waived"; }
    try {
      const list = existing.length ? existing : await this.o.gh.getIssueComments(pr.base.repo.full_name, pr.number);
      if (!hasWaiver(list, sha)) await this.o.gh.commentOnPr(pr, waiverComment(sha, why));
    } catch (e) { this.o.log(`Could not post review-waived notice on PR #${pr.number}: ${e}`, "WARNING"); return "unreviewed"; }
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
