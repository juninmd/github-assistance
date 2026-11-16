/** Advisory PR reviews (LiteLLM + opencode) for the PR Assistant: comment/label/gate only, never affects the merge decision. */
import type { RepoAutonomy } from "../../config/autonomy.ts";
import { allowsWrite } from "../../config/autonomy.ts";
import type { GithubClient, PR } from "../../github/client.ts";
import { Semaphore } from "../../utils/semaphore.ts";
import { buildLlmReviewComment, hasExistingLlmReviewComment, reviewPrWithLitellm } from "./llm-reviewer.ts";
import { hasExistingOpencodeReviewComment } from "./opencode-reviewer.ts";
import { isJules } from "./review-authors.ts";
import * as flags from "./review-flags.ts";
import { runReview } from "./review-flow.ts";
import { applyGate, gateEnabled } from "./review-gate.ts";
import { inlineComments, visibleFromPr } from "./review-lines.ts";
import { LABEL_COLORS, blocks, buildReviewComment, verdictLabel, type ReviewVerdict } from "./review-verdict.ts";

type Ai = { generate(p: string): Promise<string> } | null;
type Log = (m: string, level?: string) => void;

export class ReviewRunner {
  active: boolean;
  private slot = new Semaphore(1); // one opencode (Node) process at a time: 5 in parallel OOMKilled the pod
  private started = 0;
  constructor(private o: { gh: GithubClient; log: Log; forRepository: (r: string) => RepoAutonomy; llmClient: Ai; reviewAi: Ai; active: boolean; budget: number; waitSeconds: number }) {
    this.active = o.active;
  }

  async runLlmReview(pr: PR, comments?: any[]): Promise<void> {
    const { gh, log, llmClient } = this.o;
    if (!llmClient || hasExistingLlmReviewComment(comments ?? (await gh.getIssueComments(pr.base.repo.full_name, pr.number).catch(() => [])))) return;
    try {
      const [ok, report] = await reviewPrWithLitellm(gh, pr, llmClient);
      if (!ok) { log(`LiteLLM review skipped for PR #${pr.number}: ${report}`, "WARNING"); return; }
      const comment = buildLlmReviewComment(report);
      if (!comment) return;
      if (flags.reviewDryRun()) { log(`[DRY-RUN] LiteLLM review for PR #${pr.number}:\n${comment}`); return; }
      await gh.commentOnPr(pr, comment);
    } catch (e) { log(`LiteLLM review error on PR #${pr.number}: ${e}`, "WARNING"); }
  }

  /** opencode+skills review. Never throws, never affects merge. */
  async runOpencodeReview(pr: PR, comments?: any[]): Promise<void> {
    const { gh, log } = this.o;
    if (!this.active) return;
    let existing: any[];
    try { existing = comments ?? (await gh.getIssueComments(pr.base.repo.full_name, pr.number)); } catch { return; }
    if (hasExistingOpencodeReviewComment(existing)) return;
    if (!(await this.acquireSlot(pr))) return;
    try {
      const verdict = await runReview(gh, pr, this.o.reviewAi);
      if (!verdict) { this.active = false; log(`opencode review unavailable for PR #${pr.number}; disabled for this run`, "WARNING"); return; }
      const jules = isJules(pr.user?.login ?? "");
      const comment = buildReviewComment(verdict, pr.head?.sha ?? "", jules);
      if (flags.reviewDryRun()) { log(`[DRY-RUN] opencode review for PR #${pr.number}:\n${comment}`); return; }
      if (comment) await gh.commentOnPr(pr, comment);
      await this.postInline(pr, verdict);
      await this.applyLabel(pr, verdictLabel(verdict));
      await applyGate(pr, gh, verdict, this.gateOn(pr), log, flags.gateMinSeverity());
      log(`Reviewed PR #${pr.number}: ${verdict.verdict} (${verdictLabel(verdict)})${verdict.fixed ? " · correções enviadas" : ""}${blocks(verdict, flags.gateMinSeverity()) ? " · gate crítico" : ""}`);
    } catch (e) { this.active = false; log(`opencode review error on PR #${pr.number}: ${e}`, "WARNING"); }
    finally { this.slot.release(); }
  }
  private async postInline(pr: PR, verdict: ReviewVerdict) {
    if (!flags.enabled("REVIEW_INLINE_ENABLED", true)) return;
    try {
      const serious = verdict.findings.filter((f) => ["warn", "warning", "error"].includes(f.severity || ""));
      const comments = inlineComments(serious, await visibleFromPr(this.o.gh, pr));
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
    } catch (e) { this.o.log(`Could not apply review label '${label}' on PR #${pr.number}: ${e}`, "WARNING"); }
  }
}
