/** Conflict Resolver Agent - auto-resolves merge conflicts in pull requests and retries failing pipelines. */
import { TelegramNotifier } from "../../notifications/telegram.ts";
import type { PR } from "../../github/client.ts";
import { DEFAULT_OLLAMA_MODEL } from "../../config/settings.ts";
import { BaseAgent } from "../base-agent.ts";
import type { AgentOpts } from "../agent-types.ts";
import { ALLOWED_AUTHORS } from "../pr_assistant/agent.ts";
import { resolveConflictsAutonomously } from "../pr_assistant/conflict-resolver.ts";
import { getPipelineErrorLogs } from "../pr_assistant/logs.ts";
import { checkPipelineStatus } from "../pr_assistant/pipeline.ts";
import { MANUAL_PIPELINE_LABEL, buildMarker, fixPipelineAutonomously, maxAttempts, pipelineFixEnabled, readAttemptState } from "../pr_assistant/pipeline-fixer.ts";
import { sendManualNotice, sendPipelineFixNotice, sendPipelineManualNotice, sendResolutionNotice, sendSummaryNotice } from "./notifications.ts";

export const MANUAL_CONFLICT_LABEL = "needs-manual-conflict-resolution";
type Results = { resolved: any[]; manual: any[]; pipeline_fixed: any[]; pipeline_manual: any[]; timestamp: string };
const norm = (a: string) => a.toLowerCase().replace("[bot]", "");

export class ConflictResolverAgent extends BaseAgent {
  aiProvider: string; aiModel: string; prRef: string | null;
  constructor(o: AgentOpts) {
    super("conflict_resolver", { ...o, enforceRepositoryAllowlist: false });
    this.aiProvider = o.ai?.provider ?? "ollama"; this.aiModel = o.ai?.model ?? DEFAULT_OLLAMA_MODEL; this.prRef = o.prRef ?? null;
  }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }
  /** Overridable in tests (secondary-rate-limit backoff). */
  backoffMs = 30_000;

  async run(): Promise<Results> {
    this.log("Starting Conflict Resolver workflow");
    await this.checkRateLimit();
    const results: Results = { resolved: [], manual: [], pipeline_fixed: [], pipeline_manual: [], timestamp: new Date().toISOString() };
    if (this.prRef) { await this.handlePrRef(results); await this.sendSummary(results); return results; }
    const query = `is:pr is:open archived:false user:${this.targetOwner}`;
    this.log(`Searching PRs in your repositories with query: ${query}`);
    try { for (const issue of await this.githubClient.searchPrs(query)) await this.handleIssue(issue, results); }
    catch (e) { this.log(`Failed to search PRs: ${e}`, "ERROR"); }
    await this.sendSummary(results);
    return results;
  }
  private async handleIssue(issue: any, results: Results) {
    try { await this.handlePr(await this.githubClient.getPrFromIssue(issue), results); }
    catch (e: any) {
      if (String(e).toLowerCase().includes("secondary rate limit")) { this.log("Secondary rate limit hit - waiting 30s...", "WARNING"); await Bun.sleep(this.backoffMs); }
      this.log(`Error processing PR #${issue.number}: ${e}`, "ERROR");
    }
  }
  private async handlePrRef(results: Results) {
    try { const i = this.prRef!.lastIndexOf("#"); await this.handlePr(await this.githubClient.getPull(this.prRef!.slice(0, i), parseInt(this.prRef!.slice(i + 1), 10)), results); }
    catch (e) { this.log(`Could not resolve PR ref ${this.prRef}: ${e}`, "ERROR"); }
  }
  async handlePr(pr: PR, results: Results) {
    const repo = pr.base.repo.full_name, author = pr.user.login;
    if (!this.canWorkOnRepository(repo) || !this.isTrustedAuthor(author)) return;
    if (pr.mergeable === false) {
      if (this.hasLabel(pr, MANUAL_CONFLICT_LABEL)) { this.log(`PR #${pr.number} already flagged for manual conflict resolution; skipping`); return; }
      this.log(`Evaluating PR #${pr.number} in ${repo} by ${author}`);
      await this.processConflict(pr, results);
    } else if (pipelineFixEnabled()) await this.maybeFixPipeline(pr, results);
  }
  private hasLabel = (pr: PR, name: string) => (pr.labels ?? []).some((l: any) => (typeof l === "string" ? l : l.name) === name);
  isTrustedAuthor(author: string): boolean {
    const users = this.allowlist.listUsers(); const allowed = users.length ? users : ALLOWED_AUTHORS;
    return allowed.map(norm).includes(norm(author));
  }
  private async processConflict(pr: PR, results: Results) {
    const repo = pr.base.repo.full_name;
    this.log(`PR #${pr.number} in ${repo} has conflicts - resolving...`);
    const [ok, msg] = await resolveConflictsAutonomously(pr, { aiProvider: this.aiProvider, aiModel: this.aiModel });
    if (ok) { results.resolved.push({ pr: pr.number, repo, msg }); await this.notifyResolved(pr, msg); return; }
    results.manual.push({ pr: pr.number, repo, error: msg });
    await this.markManualResolutionNeeded(pr, msg);
  }
  private async maybeFixPipeline(pr: PR, results: Results) {
    const status = await checkPipelineStatus(this.githubClient, pr);
    if (!["failure", "error"].includes(status.state)) return;
    const comments = await this.githubClient.getIssueComments(pr.base.repo.full_name, pr.number);
    const [last] = readAttemptState(comments), mx = maxAttempts();
    if (last >= mx) { if (!this.hasLabel(pr, MANUAL_PIPELINE_LABEL)) await this.markPipelineManual(pr, `Pipeline ainda falhando após ${last} tentativas`); return; }
    this.log(`PR #${pr.number} in ${pr.base.repo.full_name} pipeline failing - fix attempt ${last + 1}/${mx}`);
    await this.processPipelineFix(pr, results, last + 1, mx);
  }
  private async processPipelineFix(pr: PR, results: Results, attempt: number, mx: number) {
    const data = await getPipelineErrorLogs(this.githubClient, pr);
    if (!data.logs.trim()) { this.log(`No actionable pipeline logs for PR #${pr.number}; skipping`, "WARNING"); return; }
    const [ok, msg, sha] = await fixPipelineAutonomously(this.githubClient, pr, data.logs, data.failed_checks, attempt, mx);
    await this.commentPipelineAttempt(pr, msg, attempt, mx, sha || pr.head.sha, ok);
    const repo = pr.base.repo.full_name;
    if (ok) { results.pipeline_fixed.push({ pr: pr.number, repo, msg }); await sendPipelineFixNotice(this.telegram, pr, msg); return; }
    results.pipeline_manual.push({ pr: pr.number, repo, error: msg });
    if (attempt >= mx) await this.markPipelineManual(pr, msg);
  }
  private async commentPipelineAttempt(pr: PR, msg: string, attempt: number, mx: number, sha: string, ok: boolean) {
    const author = pr.user?.login ?? "contributor", marker = buildMarker(attempt, sha);
    const body = `**Tentativa ${attempt}/${mx} de corrigir o pipeline**\n\n` + (ok
      ? `Ola @${author}, apliquei uma correcao automatica no pipeline.\n\n**Detalhes:** ${msg}\n\n${marker}`
      : `Ola @${author}, tentei corrigir o pipeline, mas a tentativa falhou.\n\n**Erro:** ${msg}\n\n${marker}`);
    try { await this.githubClient.commentOnPr(pr, body); } catch (e) { this.log(`Failed to send notification: ${e}`, "WARNING"); }
  }
  private async markPipelineManual(pr: PR, error: string) {
    const [ok, msg] = await this.githubClient.addLabelToPr(pr, MANUAL_PIPELINE_LABEL);
    if (ok) this.log(`Marked PR #${pr.number} in ${pr.base.repo.full_name} for manual pipeline fix`); else this.log(`Failed to label PR #${pr.number}: ${msg}`, "WARNING");
    await sendPipelineManualNotice(this.telegram, pr, error);
  }
  private async notifyResolved(pr: PR, msg: string) {
    const author = pr.user?.login ?? "contributor";
    await this.githubClient.commentOnPr(pr, `**Conflitos de merge resolvidos**\n\nOla @${author}, resolvi os conflitos automaticamente.\n\n**Detalhes:** ${msg}`);
    await sendResolutionNotice(this.telegram, pr, msg);
  }
  private async markManualResolutionNeeded(pr: PR, error: string) {
    const author = pr.user?.login ?? "contributor";
    try {
      await this.githubClient.commentOnPr(pr, `**Nao foi possivel resolver os conflitos de merge**\n\nOla @${author}, tentei resolver os conflitos automaticamente sem sucesso.\n\n**Motivo:** ${error}\n\nMantive o PR aberto e marquei para resolucao manual.`);
    } catch (e) { this.log(`Failed to close PR #${pr.number}: ${e}`, "WARNING"); }
    try {
      const esc = TelegramNotifier.escapeHtml;
      await this.telegram.sendMessage(`🚫 <b>PR ENCERRADO — CONFLITO NÃO RESOLVIDO</b>\n──────────────────────\n📦 <b>Repo:</b> <code>${esc(pr.base.repo.full_name)}</code>\n🔀 <b>PR:</b> <a href="${pr.html_url}">#${pr.number}</a> — ${esc(pr.title)}\n<pre>${esc(error.slice(0, 300))}</pre>`, "HTML");
    } catch (e) { this.log(`Failed to send unresolvable notification: ${e}`, "WARNING"); }
    const [ok, msg] = await this.githubClient.addLabelToPr(pr, MANUAL_CONFLICT_LABEL);
    if (ok) this.log(`Marked PR #${pr.number} in ${pr.base.repo.full_name} for manual resolution`); else this.log(`Failed to label PR #${pr.number}: ${msg}`, "WARNING");
    await sendManualNotice(this.telegram, pr, error);
  }
  private async sendSummary(r: Results) {
    if (r.resolved.length || r.manual.length || r.pipeline_fixed.length || r.pipeline_manual.length) await sendSummaryNotice(this.telegram, r.resolved, r.manual, r.pipeline_fixed, r.pipeline_manual);
  }
}
