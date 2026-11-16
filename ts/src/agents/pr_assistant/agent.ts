/** PR Assistant Agent - auto-merges PRs (SHA-locked, MergePolicy-gated) and manages pipelines, conflicts and advisory reviews. */
import { AutonomyPolicy } from "../../config/autonomy.ts";
import type { GithubClient, PR } from "../../github/client.ts";
import { getAiClient } from "../../ai/client.ts";
import { DEFAULT_OLLAMA_MODEL } from "../../config/settings.ts";
import { BaseAgent } from "../base-agent.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";
import type { AgentOpts } from "../agent-types.ts";
import { makeAi } from "../agent-types.ts";
import { assignOwner, requestReviewOwner } from "../core/utils.ts";
import * as billing from "./billing-gate.ts";
import { pendingWarnings } from "./comment-scan.ts";
import { llmReviewEnabled } from "./llm-reviewer.ts";
import { evaluateCommentsWithLlm } from "./merge-decision.ts";
import { MergePolicy } from "./merge-policy.ts";
import * as notify from "./notifications.ts";
import { opencodeReviewEnabled } from "./opencode-reviewer.ts";
import { NO_CI_LABEL, NO_CI_LABEL_COLOR, buildFailureComment, checkPipelineStatus, hasExistingFailureComment } from "./pipeline.ts";
import { attemptPipelineFix } from "./pipeline-fix-flow.ts";
import { ReviewRunner, type ReviewOutcome } from "./review-runner.ts";
import { buildAndSendSummary } from "./telegram-summary.ts";

export const ALLOWED_AUTHORS = ["juninmd", "Copilot", "Jules da Google", "google-labs-jules", "google-labs-jules[bot]", "gemini-code-assist", "gemini-code-assist[bot]", "imgbot[bot]", "renovate[bot]", "dependabot[bot]"];
export const BOT_REVIEWS = ["Jules da Google", "google-labs-jules", "gemini-code-assist"];
const norm = (a: string) => a.toLowerCase().replace("[bot]", "");
export const isTrustedAuthor = (login: string, allowed = ALLOWED_AUTHORS) => allowed.map(norm).includes(norm(login));
const envInt = (name: string, def: number, min = 0) => { const n = parseInt(process.env[name] || "", 10); return Number.isNaN(n) ? def : Math.max(min, n || def); };

export type Results = { merged: any[]; conflicts_resolved: any[]; pipeline_failures: any[]; skipped: any[]; blocked: any[]; timestamp?: string };
const emptyResults = (): Results => ({ merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] });
const KEYS = ["merged", "conflicts_resolved", "pipeline_failures", "skipped", "blocked"] as const;

export class PRAssistantAgent extends BaseAgent {
  targetOwner: string; minPrAgeMinutes: number; prRef: string | null; simulationMode: boolean; commentAiEnabled: boolean;
  autonomy: AutonomyPolicy; mergePolicy = new MergePolicy(); aiClient: { generate(p: string): Promise<string> } | null = null;
  reviews: ReviewRunner;

  constructor(o: AgentOpts) {
    super("pr_assistant", { ...o, enforceRepositoryAllowlist: false });
    this.targetOwner = o.targetOwner ?? "juninmd";
    this.minPrAgeMinutes = o.minPrAgeMinutes ?? 10;
    this.prRef = o.prRef ?? null;
    this.commentAiEnabled = o.commentAiEnabled ?? true;
    this.simulationMode = o.simulationMode ?? false;
    this.autonomy = new AutonomyPolicy(o.autonomyPolicyPath ?? process.env.AUTONOMY_POLICY_PATH ?? "config/autonomy.json");
    if (o.aiClient !== undefined) this.aiClient = o.aiClient;
    else if (this.commentAiEnabled) this.aiClient = makeAi(o.ai ?? { provider: "ollama", model: DEFAULT_OLLAMA_MODEL }).client;
    const litellm = () => getAiClient("litellm", { model: process.env.LLM_REVIEW_MODEL || "cloud/auto" });
    const active = o.opencodeReviewActive ?? opencodeReviewEnabled();
    this.reviews = new ReviewRunner({
      gh: this.githubClient, log: this.log, forRepository: (r) => this.autonomy.forRepository(r),
      llmClient: o.llmReviewerClient !== undefined ? o.llmReviewerClient : llmReviewEnabled() ? litellm() : null,
      reviewAi: o.reviewAiClient !== undefined ? o.reviewAiClient : active ? litellm() : null,
      active, budget: envInt("OPENCODE_REVIEW_MAX_PER_RUN", 4), waitSeconds: envInt("OPENCODE_REVIEW_WAIT_SECONDS", 120), telegram: this.telegram,
    });
  }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }
  usesRepositoryAllowlist() { return false; }

  // --- run loop -------------------------------------------------------------
  async run(): Promise<Results> {
    this.log("Starting PR Assistant workflow");
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
  async getPrsToProcess(): Promise<PR[]> {
    if (this.prRef) {
      try { const i = this.prRef.lastIndexOf("#"); return [await this.githubClient.getPull(this.prRef.slice(0, i), parseInt(this.prRef.slice(i + 1), 10))]; }
      catch (e) { this.log(`Could not resolve PR ref ${this.prRef}: ${e}`, "ERROR"); return []; }
    }
    const prs: PR[] = [];
    for (const issue of await this.githubClient.searchPrs(`is:open is:pr user:${this.targetOwner}`)) {
      try { prs.push(await this.githubClient.getPrFromIssue(issue)); } catch (e) { this.log(`Could not resolve PR from issue: ${e}`, "WARNING"); }
    }
    return prs;
  }
  async processPr(pr: PR, results: Results): Promise<void> {
    const repo = pr.base.repo.full_name;
    this.log(`Processing PR #${pr.number} in ${repo}`);
    // Before any skip: Jules-opened PRs are never created by this app, so this is their only assignment point.
    await assignOwner(this.githubClient, pr, this.targetOwner, this.log);
    await requestReviewOwner(this.githubClient, pr, this.targetOwner, this.log);
    if (this.skipYoung(pr, results, repo) || this.skipLabeled(pr, results, repo) || this.skipUntrusted(pr, results, repo)) return;
    const status = await checkPipelineStatus(this.githubClient, pr);
    if (status.no_ci) await this.tagNoCi(pr);
    await this.tryAcceptSuggestions(pr);
    const comments = await this.githubClient.getIssueComments(repo, pr.number);
    await this.warnExposedSecrets(pr, comments);
    const resolved = await this.resolveMergeable(pr, repo);
    if (!resolved) { results.skipped.push({ pr: pr.number, title: pr.title, reason: "mergeable_unknown", repository: repo }); return; }
    pr = resolved;
    if (pr.mergeable === false) { await this.handleConflicts(pr, results, comments); return; }
    // Review first: a merged PR can never be reviewed afterwards (that is how fast merges went out unreviewed).
    let review: ReviewOutcome = "none";
    if (!this.simulationMode) { await this.reviews.runLlmReview(pr, comments); review = await this.reviews.runOpencodeReview(pr, comments); }
    const skipped = await this.handlePipelineAndSkip(pr, results, comments, status);
    if (skipped) return;
    if (review !== "none") { this.recordSkip(results, pr.number, pr.title, repo, review === "blocked" ? "review_blocked" : "review_pending"); return; }
    await this.tryMerge(pr, results, comments);
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
      if (await attemptPipelineFix(pr, this.githubClient, this.log)) { this.recordSkip(results, pr.number, pr.title, repo, "pipeline_fix_attempted"); return true; }
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
    const d = await evaluateCommentsWithLlm(this.aiClient, list, this.isTrusted);
    return [d.decision === "merge", d.reason];
  }
  async tryMerge(pr: PR, results: Results, comments: any[]): Promise<void> {
    const repo = pr.base.repo.full_name, gh: GithubClient = this.githubClient;
    const autonomy = this.autonomy.forRepository(repo);
    const [should, reason] = await this.evaluateComments(pr, comments);
    // Rejection or evaluator unavailability blocks/waits — never close the PR.
    if (!should) { results.skipped.push({ pr: pr.number, title: pr.title, reason, repository: repo }); return; }
    if (!(autonomy.merge && autonomy.mode === "merge")) { this.recordBlocked(results, pr, repo, `autonomy_mode:${autonomy.mode}`); return; }
    if (this.simulationMode) { this.log(`[SIMULATION] would merge PR #${pr.number} in ${repo}`); results.skipped.push({ pr: pr.number, title: pr.title, reason: "simulation", repository: repo }); return; }
    const ms = pr.mergeable_state;
    if (ms === null || ms === undefined || ms === "unknown") { this.recordBlocked(results, pr, repo, "mergeable_state_unknown"); return; }
    let newSha = "";
    // update-branch 422s on an up-to-date branch, so only call it when GitHub says behind.
    if (ms === "behind") {
      const [ok, msg, sha] = await gh.updatePrBranch(pr);
      if (!ok) { this.recordBlocked(results, pr, repo, `update_branch_failed: ${msg}`); return; }
      newSha = sha;
    }
    try { pr = await gh.getPull(repo, pr.number); } catch (e) { this.recordBlocked(results, pr, repo, `refresh_failed: ${e}`); return; }
    const expected = newSha || pr.head.sha;
    const status = await checkPipelineStatus(gh, pr);
    const decision = this.mergePolicy.evaluate({ status, expectedSha: expected, currentSha: pr.head.sha, autonomy });
    if (decision.action !== "merge") { this.recordBlocked(results, pr, repo, decision.reasons.join("|"), expected); return; }
    if (billing.isBillingBlocked(status)) {
      const leaks = await billing.scanAddedLines(gh, pr);
      if (leaks.length) { this.recordBlocked(results, pr, repo, `billing_blocked_credential_found: ${leaks.slice(0, 5).map((h) => `${h.file}:${h.line} -> ${h.rule_id}`).join("; ")}`, expected); return; }
      await this.postBillingDisclaimer(pr, status, expected, comments);
    }
    const [ok, msg] = await gh.mergePr(pr, "squash", expected);
    if (ok) {
      results.merged.push({ action: "merged", pr: pr.number, title: pr.title, repository: repo, sha: expected });
      if (!this.simulationMode) await notify.notifyMerged(gh, pr, comments);
      await this.telegram.sendPrNotification(pr);
    } else {
      if (!this.simulationMode) await notify.notifyMergeFailed(gh, this.telegram, pr, msg, comments);
      results.skipped.push({ pr: pr.number, title: pr.title, reason: "merge_failed", error: msg, repository: repo });
    }
  }
  async postBillingDisclaimer(pr: PR, status: Record<string, any>, sha: string, comments?: any[]) {
    try {
      const list = comments ?? (await this.githubClient.getIssueComments(pr.base.repo.full_name, pr.number));
      if (billing.hasDisclaimer(list)) return;
      await this.githubClient.commentOnPr(pr, billing.buildDisclaimer((status.billing_checks ?? []).filter((c: any) => typeof c === "string"), sha));
    } catch (e) { this.log(`Could not post billing disclaimer on PR #${pr.number}: ${e}`, "WARNING"); }
  }

  // --- conflicts / notifications --------------------------------------------
  async handleConflicts(pr: PR, results: Results, comments?: any[]) {
    results.skipped.push({ pr: pr.number, title: pr.title, reason: "has_conflicts", repository: pr.base.repo.full_name });
    if (!this.simulationMode) await notify.notifyConflicts(this.githubClient, this.telegram, pr, comments);
  }
  notifyConflictResolved(pr: PR, msg: string) { return notify.notifyConflictResolved(this.githubClient, this.telegram, pr, msg); }
}
