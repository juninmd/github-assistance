/** Jules Tracker - monitors active Jules sessions, answers questions and approves plans. */
import { BaseAgent } from "../base-agent.ts";
import { makeAi, type AgentOpts } from "../agent-types.ts";
import type { AIClient } from "../../ai/client.ts";
import { assignOwner, ROADMAP_ACTIVE_LABEL, ROADMAP_LABEL, issueHasLabel } from "../core/utils.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";
import * as u from "./utils.ts";

type R = Record<string, any>;
const QUESTION_COLOR = "\x1b[96m", ANSWER_COLOR = "\x1b[92m", RESET = "\x1b[0m";
const ACTIVE = new Set(["IN_PROGRESS", "AWAITING_USER_FEEDBACK"]);

export class JulesTrackerAgent extends BaseAgent {
  aiClient: AIClient | null = null;
  constructor(o: AgentOpts) {
    super("jules_tracker", { ...o, enforceRepositoryAllowlist: false });
    if (o.aiClient !== undefined) this.aiClient = o.aiClient;
    else if (o.aiEnabled ?? true) this.aiClient = makeAi({ provider: o.ai?.provider ?? "litellm", model: o.ai?.model ?? "cloud/auto", config: o.ai?.config }).client;
  }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  async run() {
    this.log("Starting Jules Tracker workflow");
    // No GitHub calls here: tracking must keep clearing sessions even when GH_PAT is expired.
    const repositories = this.allowlist.listRepositories();
    const results: R = { answered_questions: [], reviewed_plans: [], failed: [] };
    let sessions: R[];
    try { sessions = await this.julesClient.listSessions({ pageSize: 50, maxPages: 1 }); }
    catch {
      this.log("Failed to list sessions", "ERROR"); results.failed.push({ error: "Failed to list sessions" });
      await this.telegram.sendMessage("❌ <b>JULES TRACKER — ERRO AO LISTAR SESSÕES</b>\n<pre>Verifique os logs para detalhes.</pre>", "HTML");
      return results;
    }
    for (const session of sessions.filter((s) => ACTIVE.has(s.state ?? s.status))) {
      const id = session.id || session.name;
      if (!id) continue;
      const name = u.extractRepositoryName(session);
      const repo = this.usesRepositoryAllowlist() ? repositories.find((r) => r === name) : name;
      if (!repo) continue;
      try { await this.handleSession(id, repo, session, results); }
      catch (e: any) {
        this.log(`Failed to process session ${id}: ${e?.message ?? e}`, "ERROR"); results.failed.push({ session_id: id, error: String(e?.message ?? e) });
        await this.telegram.sendMessage(`❌ <b>JULES TRACKER — ERRO SESSÃO</b>\n🆔 <code>${TelegramNotifier.escapeHtml(String(id))}</code>\n<pre>Verifique os logs para detalhes.</pre>`, "HTML");
      }
    }
    this.log(`Completed: answered ${results.answered_questions.length} questions`);
    // Isolated: the roadmap step is the first GitHub call; its failure must never affect the work above.
    results.roadmap_started = [];
    try { await this.advanceRoadmapIssues(results); } catch (e: any) { this.log(`Roadmap advancement skipped: ${e?.message ?? e}`, "WARNING"); }
    await this.sendSummary(results);
    if (results.failed.length) results.status = "failed";
    return results;
  }

  private async handleSession(id: string, repo: string, session: R, results: R) {
    const activities = await this.julesClient.listActivities(id);
    if (u.isPlanPending(activities)) { await this.handlePlanApproval(id, repo, session, activities, results); return; }
    let question = u.getPendingQuestion(session, activities);
    if (!question) {
      if ((session.state ?? session.status) !== "AWAITING_USER_FEEDBACK" || u.latestActivityIsUserReply(activities)) return;
      question = "Jules is awaiting user feedback but no specific question was detected."; // blocked without a clear question — unblock
    }
    const url = session.url || "";
    const description = u.formatQuestionDescription(repo, id, question);
    this.log(u.formatQuestionLog(repo, id, url, question, QUESTION_COLOR, RESET));
    const prompt = `You are the user interacting with an AI developer agent (Jules).\nRepository: ${repo}\nSession: ${id}\nSession URL: ${url}\n\nJules has asked the following question or is waiting for input:\n"${question}"\n\nPlease provide a helpful, concise, and direct answer so Jules can continue its work.\nIf you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.`;
    let answer = u.DEFAULT_UNBLOCKING_ANSWER;
    if (this.aiClient) { try { answer = await this.aiClient.generate(prompt); } catch (e: any) { this.log(`AI answer failed for session ${id}; using default unblock answer: ${e?.message ?? e}`, "WARNING"); } }
    answer = u.ensureOpenPrRequest(answer);
    this.log(u.formatAnswerLog(answer, ANSWER_COLOR, RESET));
    await this.julesClient.sendMessage(id, answer);
    await u.sendTelegramUpdate(this.telegram, repo, id, url, question, answer);
    results.answered_questions.push({ session_id: id, session_url: url, repository: repo, question_description: description, question, answer });
  }

  /** Label every open roadmap issue 'jules' (natively triggers a Jules session) and assign the owner; all items run in parallel. */
  private async advanceRoadmapIssues(results: R) {
    for (const repository of this.allowlist.listRepositories()) {
      try {
        if (!(await this.getRepositoryInfo(repository))) continue;
        for (const issue of await this.githubClient.getOpenIssues(repository, 1000)) {
          if (!issueHasLabel(issue, ROADMAP_LABEL)) continue;
          await assignOwner(this.githubClient, issue, this.targetOwner, this.log);
          if (issueHasLabel(issue, ROADMAP_ACTIVE_LABEL)) continue;
          await this.githubClient.post(`/repos/${repository}/issues/${issue.number}/labels`, { labels: [ROADMAP_ACTIVE_LABEL] });
          this.log(`Started roadmap item #${issue.number} for ${repository}`);
          results.roadmap_started.push({ repository, issue: issue.number, url: issue.html_url });
        }
      } catch (e: any) { this.log(`Failed to advance roadmap for ${repository}: ${e?.message ?? e}`, "WARNING"); }
    }
  }

  private async handlePlanApproval(id: string, repo: string, session: R, activities: R[], results: R) {
    const url = session.url || "";
    const plan = u.getPendingPlan(activities) || String(session.statusMessage ?? "").trim();
    if (!plan) return;
    const prompt = `You are the user reviewing an implementation plan proposed by an AI developer agent (Jules).\nRepository: ${repo}\nSession: ${id}\n\nJules proposed the following plan and is waiting for approval before starting work:\n"""${plan}"""\n\nIf the plan looks safe and reasonable, respond with EXACTLY: APPROVE\nOtherwise, respond with the concise feedback/changes Jules should apply before proceeding (do not include the word APPROVE).`;
    let decision = "APPROVE";
    if (this.aiClient) { try { decision = (await this.aiClient.generate(prompt)).trim(); } catch (e: any) { this.log(`AI plan review failed for session ${id}; approving by default: ${e?.message ?? e}`, "WARNING"); } }
    let action: string;
    if (decision.toUpperCase().startsWith("APPROVE")) { await this.julesClient.approvePlan(id); await this.julesClient.sendMessage(id, u.OPEN_PR_INSTRUCTION); action = "approved"; }
    else { decision = u.ensureOpenPrRequest(decision); await this.julesClient.sendMessage(id, decision); action = "changes_requested"; }
    await u.sendPlanTelegramUpdate(this.telegram, repo, id, url, plan, decision);
    results.reviewed_plans.push({ session_id: id, session_url: url, repository: repo, action });
  }

  private async sendSummary(r: R) {
    const esc = TelegramNotifier.escapeHtml;
    const lines = ["🤖 <b>JULES TRACKER</b>", "──────────────────────", `💬 <b>Perguntas respondidas:</b> <code>${r.answered_questions.length}</code>`, `📋 <b>Planos revisados:</b> <code>${r.reviewed_plans.length}</code>`, `🗺️ <b>Itens de roadmap iniciados:</b> <code>${r.roadmap_started.length}</code>`, `❌ <b>Falhas:</b> <code>${r.failed.length}</code>`];
    for (const it of r.answered_questions.slice(0, 5)) lines.push(`  └ <a href="${esc(it.session_url ?? "")}">${esc(it.repository ?? "")}</a>`);
    for (const it of r.roadmap_started.slice(0, 5)) lines.push(`  └ 🗺️ <a href="${esc(it.url ?? "")}">${esc(it.repository ?? "")} #${it.issue}</a>`);
    await this.telegram.sendMessage(lines.join("\n"), "HTML");
  }
}
