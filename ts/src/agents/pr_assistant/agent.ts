/** PR Assistant Agent - auto-merges PRs (SHA-locked, MergePolicy-gated) and manages pipelines, conflicts and advisory reviews. */
import { AutonomyPolicy } from "../../config/autonomy.ts";
import type { PR } from "../../github/client.ts";
import { DEFAULT_OLLAMA_MODEL } from "../../config/settings.ts";
import { BaseAgent } from "../base-agent.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";
import type { AgentOpts } from "../agent-types.ts";
import { makeAi } from "../agent-types.ts";
import { assignOwner, mapLimit, requestReviewOwner } from "../core/utils.ts";
import * as billing from "./billing-gate.ts";
import { pendingWarnings } from "./comment-scan.ts";
import { evaluateCommentsWithLlm } from "./merge-decision.ts";
import { MergePolicy } from "./merge-policy.ts";
import * as mergeFlow from "./merge-flow.ts";
import * as notify from "./notifications.ts";
import { opencodeReviewEnabled } from "./opencode-reviewer.ts";
import { NO_CI_LABEL, NO_CI_LABEL_COLOR, buildFailureComment, checkPipelineStatus, hasExistingFailureComment } from "./pipeline.ts";
import { attemptPipelineFix } from "./pipeline-fix-flow.ts";
import { enabled as flagEnabled } from "./review-flags.ts";
import { botAuthActive, botLogin } from "../../github/bot-auth.ts";
import { reviewerLogins } from "./bot-identity.ts";
import { mustWaitForChecks } from "./checks-wait.ts";
import { clearManualConflictLabel, handleConflict, type Resolver } from "./conflict-flow.ts";
import { hasLabel, KEEP_DRAFT_LABEL } from "../core/pr-options.ts";
import { resolveConflictsAutonomously } from "./conflict-resolver.ts";
import { laneAllowsMerge } from "./dependency-lane.ts";
import { runLocalChecks, type LocalChecks } from "./local-checks.ts";
import { headCommitAt, mergeCommandValid, ownerCommands, type OwnerCommands } from "./owner-commands.ts";
import { OPENCODE_REVIEW_MARKER } from "./opencode-reviewer.ts";
import { withPrLock } from "./pr-lock.ts";
import { ReviewRunner, type ReviewOutcome } from "./review-runner.ts";
import { buildAndSendSummary } from "./telegram-summary.ts";

export const ALLOWED_AUTHORS = ["juninmd", "Copilot", "gemini-code-assist", "gemini-code-assist[bot]", "imgbot[bot]", "renovate[bot]", "dependabot[bot]"];
export const BOT_REVIEWS = ["gemini-code-assist"];
/** Exact login match: a human account named like a bot (`dependabot` vs `dependabot[bot]`) must not inherit its trust. */
export const isTrustedAuthor = (login: string, allowed = ALLOWED_AUTHORS) => allowed.map((a) => a.toLowerCase()).includes((login ?? "").trim().toLowerCase());
const envInt = (name: string, def: number, min = 0) => { const n = parseInt(process.env[name] || "", 10); return Number.isNaN(n) ? def : Math.max(min, n || def); };

export type Results = { merged: any[]; conflicts_resolved: any[]; pipeline_failures: any[]; skipped: any[]; blocked: any[]; timestamp?: string };
const emptyResults = (): Results => ({ merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] });
const KEYS = ["merged", "conflicts_resolved", "pipeline_failures", "skipped", "blocked"] as const;

export class PRAssistantAgent extends BaseAgent {
  targetOwner: string; minPrAgeMinutes: number; prRef: string | null; simulationMode: boolean; commentAiEnabled: boolean;
  autonomy: AutonomyPolicy; mergePolicy = new MergePolicy(); aiClient: { generate(p: string): Promise<string> } | null = null;
  reviews: ReviewRunner; requireReview: boolean; localChecks: LocalChecks; resolveConflicts: Resolver;
  /** Authors whose review comments count as the verdict (see bot-identity.ts); the live App login is added at run start. */
  readonly reviewerList: string[];
  get reviewers() { return this.reviewerList; }

  constructor(o: AgentOpts) {
    super("pr_assistant", { ...o, enforceRepositoryAllowlist: false });
    this.targetOwner = o.targetOwner ?? "juninmd";
    this.minPrAgeMinutes = o.minPrAgeMinutes ?? 10;
    this.prRef = o.prRef ?? null;
    this.commentAiEnabled = o.commentAiEnabled ?? true;
    this.simulationMode = o.simulationMode ?? false;
    this.requireReview = o.requireReview ?? flagEnabled("MERGE_REQUIRE_REVIEW", true);
    this.reviewerList = reviewerLogins(this.targetOwner, null, botAuthActive());
    this.localChecks = o.localChecks ?? runLocalChecks;
    this.resolveConflicts = o.resolveConflicts ?? ((pr) => resolveConflictsAutonomously(pr));
    this.autonomy = new AutonomyPolicy(o.autonomyPolicyPath ?? process.env.AUTONOMY_POLICY_PATH ?? "config/autonomy.json");
    if (o.aiClient !== undefined) this.aiClient = o.aiClient;
    else if (this.commentAiEnabled) this.aiClient = makeAi(o.ai ?? { provider: "ollama", model: DEFAULT_OLLAMA_MODEL }).client;
    const active = o.opencodeReviewActive ?? opencodeReviewEnabled();
    this.reviews = new ReviewRunner({
      gh: this.githubClient, log: this.log, forRepository: (r) => this.autonomy.forRepository(r),
      active, budget: envInt("OPENCODE_REVIEW_MAX_PER_RUN", 4), waitSeconds: envInt("OPENCODE_REVIEW_WAIT_SECONDS", 120), reviewers: this.reviewers, telegram: this.telegram,
    });
  }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }
  usesRepositoryAllowlist() { return false; }

  // --- run loop -------------------------------------------------------------
  async run(): Promise<Results> {
    this.log("Starting PR Assistant workflow");
    await this.resolveBotLogin();
    const results: Results = { ...emptyResults(), timestamp: new Date().toISOString() };
    const prs = await this.getPrsToProcess();
    const queue = [...prs];
    const worker = async () => {
      for (let pr = queue.shift(); pr; pr = queue.shift()) {
        const local = emptyResults();
        try { await this.processPr(pr, local); }
        catch (e: any) {
          this.log(`Error processing PR #${pr.number}: ${e}`, "ERROR");
          local.skipped.push({ pr: pr.number, title: pr.title ?? "Unknown Title", reason: "error", error: String(e?.message ?? e) });
          try {
            const esc = TelegramNotifier.escapeHtml;
            await this.telegram.sendMessage(`❌ <b>PR ASSISTANT — ERRO</b>\n──────────────────────\n📦 <b>Repo:</b> <code>${esc(pr.base?.repo?.full_name ?? "unknown")}</code>  PR: <code>#${pr.number}</code>\n<pre>${esc(String(e?.message ?? e).slice(0, 300))}</pre>`, "HTML");
          } catch { /* best-effort */ }
        }
        for (const k of KEYS) results[k].push(...local[k]);
      }
    };
    await Promise.all(Array.from({ length: Math.min(5, prs.length) }, worker));
    await buildAndSendSummary(results as any, this.telegram, this.targetOwner);
    return results;
  }
  /** Read the App's real login (`<slug>[bot]`) so an App rename can never silently stop approvals from counting. */
  async resolveBotLogin(): Promise<void> {
    try {
      const live = await botLogin();
      if (live && !this.reviewerList.map((r) => r.toLowerCase()).includes(live.toLowerCase())) { this.reviewerList.unshift(live); this.log(`Bot login resolved: ${live}`); }
    } catch (e) { this.log(`Could not resolve the App login (${e}); using configured reviewers`, "WARNING"); }
  }
  async getPrsToProcess(): Promise<PR[]> {
    if (this.prRef) {
      try { const i = this.prRef.lastIndexOf("#"); return [await this.githubClient.getPull(this.prRef.slice(0, i), parseInt(this.prRef.slice(i + 1), 10))]; }
      catch (e) { this.log(`Could not resolve PR ref ${this.prRef}: ${e}`, "ERROR"); return []; }
    }
    const issues = await this.githubClient.searchPrs(`is:open is:pr archived:false user:${this.targetOwner}`);
    const resolved = await mapLimit(issues, 8, async (issue) => {
      try { return await this.githubClient.getPrFromIssue(issue); } catch (e) { this.log(`Could not resolve PR from issue: ${e}`, "WARNING"); return null; }
    });
    return resolved.filter((p): p is PR => p !== null);
  }
  async processPr(pr: PR, results: Results): Promise<void> {
    const repo = pr.base.repo.full_name;
    this.log(`Processing PR #${pr.number} in ${repo}`);
    // Before any skip: PRs opened by other tools are never created by this app, so this is their only assignment point.
    await Promise.all([assignOwner(this.githubClient, pr, this.targetOwner, this.log), requestReviewOwner(this.githubClient, pr, this.targetOwner, this.log)]);
    if (this.skipYoung(pr, results, repo) || this.skipLabeled(pr, results, repo) || this.skipUntrusted(pr, results, repo)) return;
    const [status, comments] = await Promise.all([checkPipelineStatus(this.githubClient, pr), this.githubClient.getIssueComments(repo, pr.number)]);
    const cmds = ownerCommands(comments, this.targetOwner);
    if (cmds.hold) { this.recordSkip(results, pr.number, pr.title, repo, "owner_hold"); return; }
    // Owner `/review` or `/merge` skips the wait; otherwise no model work while any check of this head is still running.
    if (cmds.reviewAt === null && cmds.mergeAt === null && status.state === "pending" && mustWaitForChecks(status, await headCommitAt(this.githubClient, pr))) {
      this.log(`PR #${pr.number}: waiting for ${status.pending_checks.length} pending check(s)`);
      this.recordSkip(results, pr.number, pr.title, repo, "checks_pending"); return;
    }
    // Builder PRs: reviewed like any other, but never marked ready nor merged by the bot (not even on `/merge`).
    if (hasLabel(pr, KEEP_DRAFT_LABEL)) {
      if (!this.simulationMode) await this.reviews.runOpencodeReview(pr, comments, { force: this.reviewForced(cmds, comments) });
      this.recordSkip(results, pr.number, pr.title, repo, "keep_draft"); return;
    }
    if (status.no_ci) await this.tagNoCi(pr);
    await this.tryAcceptSuggestions(pr);
    await this.warnExposedSecrets(pr, comments);
    const resolved = await this.resolveMergeable(pr, repo);
    if (!resolved) { results.skipped.push({ pr: pr.number, title: pr.title, reason: "mergeable_unknown", repository: repo }); return; }
    pr = resolved;
    await clearManualConflictLabel(this.githubClient, pr, this.log);
    if (pr.mergeable === false) { await this.handleConflicts(pr, results, comments); return; }
    // Cheap gates before the model: a red pipeline gets fixed (new SHA, new review) instead of reviewed now.
    if (["failure", "error"].includes(status.state)) { await this.handlePipelineAndSkip(pr, results, comments, status); return; }
    // Owner `/merge` written after the newest commit is an explicit human approval of this exact head.
    if (cmds.mergeAt !== null && mergeCommandValid(cmds, cmds.mergeSha ? null : await headCommitAt(this.githubClient, pr), pr.head.sha)) { await this.ownerMerge(pr, results, comments, status); return; }
    // Review first: a merged PR can never be reviewed afterwards (that is how fast merges went out unreviewed).
    let review: ReviewOutcome = "unreviewed";
    if (!this.simulationMode) review = await this.reviews.runOpencodeReview(pr, comments, { force: this.reviewForced(cmds, comments) });
    const skipped = await this.handlePipelineAndSkip(pr, results, comments, status);
    if (skipped) return;
    if (review === "skipped") { // dependency bots: light lane instead of a model review
      const lane = await laneAllowsMerge(this.githubClient, pr, status);
      if (!lane.ok) { this.recordSkip(results, pr.number, pr.title, repo, lane.reason); return; }
      await this.tryMerge(pr, results, comments, true); return;
    }
    if (review === "waived") { // the breaker path never ran runReview's credential gate: scan here before merging unreviewed
      const leaks = await billing.scanAddedLines(this.githubClient, pr);
      if (leaks.length) { this.recordBlocked(results, pr, repo, `waived_credential_found: ${leaks.slice(0, 3).map((h) => `${h.file}:${h.line}`).join("; ")}`); return; }
      await this.tryMerge(pr, results, comments, true); return;
    }
    if (this.requireReview ? review !== "approved" : review === "blocked" || review === "deferred") {
      this.recordSkip(results, pr.number, pr.title, repo, { blocked: "review_blocked", deferred: "review_pending", unreviewed: "review_unavailable", waived: "review_unavailable", approved: "review_blocked", skipped: "review_skipped" }[review]); return;
    }
    // The review may have pushed a fix; merge the PR as it is now, not the stale snapshot.
    if (this.requireReview) { try { pr = await this.githubClient.getPull(repo, pr.number); } catch { /* tryMerge re-checks approval against this snapshot */ } }
    await this.tryMerge(pr, results, comments);
  }

  /** `/review` newer than the newest bot review comment forces a fresh verdict. */
  reviewForced(cmds: OwnerCommands, comments: any[]): boolean {
    if (cmds.reviewAt === null) return false;
    const last = Math.max(0, ...comments.filter((c) => (c.body ?? "").includes(OPENCODE_REVIEW_MARKER)).map((c) => Date.parse(c.created_at ?? "") || 0));
    return cmds.reviewAt > last;
  }
  async ownerMerge(pr: PR, results: Results, comments: any[], status: Record<string, any>) {
    const repo = pr.base.repo.full_name;
    if (await this.handlePipelineAndSkip(pr, results, comments, status)) return;
    const leaks = await billing.scanAddedLines(this.githubClient, pr);
    if (leaks.length) { this.recordBlocked(results, pr, repo, `owner_merge_credential_found: ${leaks.slice(0, 3).map((h) => `${h.file}:${h.line}`).join("; ")}`); return; }
    this.log(`PR #${pr.number}: owner /merge accepted for ${pr.head.sha.slice(0, 8)}`);
    await this.tryMerge(pr, results, comments, true);
  }

  // --- skips ----------------------------------------------------------------
  recordSkip(results: Results, n: number, title: string, repo: string, reason: string) { results.skipped.push({ pr: n, title, reason, repository: repo }); }
  isOldEnough(pr: PR): boolean { return !pr.created_at || Date.now() - new Date(pr.created_at).getTime() >= this.minPrAgeMinutes * 60_000; }
  skipYoung(pr: PR, r: Results, repo: string) { if (this.isOldEnough(pr)) return false; this.recordSkip(r, pr.number, pr.title, repo, "pr_too_young"); return true; }
  skipLabeled(pr: PR, r: Results, repo: string) {
    if (!(pr.labels ?? []).some((l: any) => (typeof l === "string" ? l : l.name) === "auto-merge-skip")) return false;
    this.recordSkip(r, pr.number, pr.title, repo, "auto-merge-skip"); return true;
  }
  isTrusted = (login: string) => isTrustedAuthor(login);
  skipUntrusted(pr: PR, r: Results, repo: string) { if (this.isTrusted(pr.user?.login ?? "unknown")) return false; this.recordSkip(r, pr.number, pr.title, repo, "untrusted_author"); return true; }
  async tagNoCi(pr: PR) {
    try {
      const repo = pr.base.repo.full_name;
      if (!(await this.githubClient.getLabels(repo)).some((l: any) => l.name.toLowerCase() === NO_CI_LABEL.toLowerCase()))
        await this.githubClient.createLabel(repo, { name: NO_CI_LABEL, color: NO_CI_LABEL_COLOR, description: "Repositório sem CI configurado" });
      await this.githubClient.addLabelToPr(pr, NO_CI_LABEL);
    } catch (e) { this.log(`Could not add '${NO_CI_LABEL}' label on PR #${pr.number}: ${e}`, "WARNING"); }
  }
  async tryAcceptSuggestions(pr: PR) {
    if (this.simulationMode) return;
    try { const [, , n] = await this.githubClient.acceptReviewSuggestions(pr, BOT_REVIEWS); if (n > 0) this.log(`Applied ${n} suggestions on PR #${pr.number}`); }
    catch (e) { this.log(`Error applying suggestions on PR #${pr.number}: ${e}`, "WARNING"); }
  }
  async warnExposedSecrets(pr: PR, comments: any[]) {
    if (this.simulationMode) return;
    try { for (const body of pendingWarnings(comments)) await this.githubClient.commentOnPr(pr, body); }
    catch (e) { this.log(`Comment secret scan failed on PR #${pr.number}: ${e}`, "WARNING"); }
  }

  // --- pipeline -------------------------------------------------------------
  async handlePipelineAndSkip(pr: PR, results: Results, comments: any[], status?: Record<string, any>): Promise<boolean> {
    status ||= await checkPipelineStatus(this.githubClient, pr);
    const state = status.state, repo = pr.base.repo.full_name;
    if (state === "failure" || state === "error") {
      // Try to fix the pipeline at least once before just warning the author.
      const fixed = await withPrLock(this.githubClient, pr, () => attemptPipelineFix(pr, this.githubClient, this.log));
      if (fixed === null) { this.recordSkip(results, pr.number, pr.title, repo, "pr_busy"); return true; }
      if (fixed) { this.recordSkip(results, pr.number, pr.title, repo, "pipeline_fix_attempted"); return true; }
      await this.warnPipelineFailure(pr, status, results, comments);
      this.recordSkip(results, pr.number, pr.title, repo, "pipeline_failure");
      return true;
    }
    if (state !== "success") {
      // No CI checks at all: nothing pending or failing. Let the merge policy decide and still run the review.
      if ((status.checks?.total ?? 0) === 0) return false;
      if (!this.simulationMode) await notify.notifyPipelinePending(this.githubClient, this.telegram, pr, state, comments);
      this.recordSkip(results, pr.number, pr.title, repo, `pipeline_${state}`);
      return true;
    }
    return false;
  }
  async warnPipelineFailure(pr: PR, status: Record<string, any>, results: Results, comments: any[]) {
    results.pipeline_failures.push({ action: "pipeline_failure", pr: pr.number, title: pr.title, state: status.state, repository: pr.base.repo.full_name });
    if (this.simulationMode || hasExistingFailureComment(comments)) return;
    try { await this.githubClient.commentOnPr(pr, buildFailureComment(pr, status.failed_checks ?? [])); }
    catch (e) { this.log(`Failed to post pipeline-failure comment on PR #${pr.number}: ${e}`, "WARNING"); }
  }

  // --- merge ----------------------------------------------------------------
  async resolveMergeable(pr: PR, repo: string): Promise<PR | null> {
    if (pr.mergeable !== null && pr.mergeable !== undefined) return pr;
    await Bun.sleep(this.mergeableWaitMs);
    try { pr = await this.githubClient.getPull(repo, pr.number); } catch (e) { this.log(`Failed to re-fetch PR #${pr.number}: ${e}`, "WARNING"); }
    return pr.mergeable !== null && pr.mergeable !== undefined ? pr : null;
  }
  mergeableWaitMs = 3000;
  recordBlocked(results: Results, pr: PR, repo: string, reason: string, sha?: string) {
    results.blocked.push({ pr: pr.number, title: pr.title, reason, repository: repo, ...(sha ? { sha } : {}) });
  }
  async evaluateComments(pr: PR, comments?: any[]): Promise<[boolean, string]> {
    let list: any[];
    try { list = comments ?? (await this.githubClient.getIssueComments(pr.base.repo.full_name, pr.number)); } catch (e) { return [false, `evaluator_unavailable: ${e}`]; }
    const d = await evaluateCommentsWithLlm(this.aiClient, list, this.isTrusted, this.targetOwner);
    return [d.decision === "merge", d.reason];
  }
  tryMerge(pr: PR, results: Results, comments: any[], reviewExempt = false): Promise<void> { return mergeFlow.tryMerge(this, pr, results, comments, reviewExempt); }
  reviewApproved(pr: PR): Promise<boolean> { return mergeFlow.reviewApproved(this, pr); }
  // --- conflicts / notifications --------------------------------------------
  /** Conflicts are handled in this same cycle: dependabot rebases itself, others are resolved inline under the PR lease. */
  async handleConflicts(pr: PR, results: Results, comments: any[] = []) {
    const repo = pr.base.repo.full_name;
    if (this.simulationMode) { results.skipped.push({ pr: pr.number, title: pr.title, reason: "has_conflicts", repository: repo }); return; }
    if (!flagEnabled("PR_ASSISTANT_RESOLVE_CONFLICTS", true)) {
      results.skipped.push({ pr: pr.number, title: pr.title, reason: "has_conflicts", repository: repo });
      await notify.notifyConflicts(this.githubClient, this.telegram, pr, comments); return;
    }
    const out = await handleConflict(this.githubClient, this.telegram, pr, comments, this.resolveConflicts, this.log);
    if (out.kind === "resolved") {
      results.conflicts_resolved.push({ pr: pr.number, title: pr.title, repository: repo, message: out.msg });
      await this.notifyConflictResolved(pr, out.msg); return;
    }
    const reason = { rebase_requested: "dependabot_rebase_requested", rebase_pending: "dependabot_rebase_requested", manual: "has_conflicts", busy: "pr_busy", labelled: "has_conflicts" }[out.kind];
    results.skipped.push({ pr: pr.number, title: pr.title, reason, repository: repo, ...(out.kind === "manual" ? { error: out.msg } : {}) });
  }
  notifyConflictResolved(pr: PR, msg: string) { return notify.notifyConflictResolved(this.githubClient, this.telegram, pr, msg); }
}
