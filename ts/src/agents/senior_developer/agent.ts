/** Senior Developer - coordinates repository analysis and opencode task creation. */
import { BaseAgent } from "../base-agent.ts";
import { makeAi, type AgentOpts } from "../agent-types.ts";
import type { AIClient } from "../../ai/client.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";
import { SeniorDeveloperAnalyzer } from "./analyzers.ts";
import { SeniorDeveloperBurstManager } from "./burst-manager.ts";
import { ANALYSIS_METHODS, SeniorDeveloperTaskCreator } from "./task-creator.ts";

const TASK_KEYS = ["feature_tasks", "security_tasks", "cicd_tasks", "tech_debt_tasks", "modernization_tasks", "performance_tasks"];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class SeniorDeveloperAgent extends BaseAgent {
  aiClient: AIClient; analyzer: SeniorDeveloperAnalyzer; taskCreator: SeniorDeveloperTaskCreator; burstMgr: SeniorDeveloperBurstManager;
  constructor(o: AgentOpts) {
    super("senior_developer", { ...o, enforceRepositoryAllowlist: true });
    this.aiClient = o.aiClient ?? makeAi(o.ai).client;
    this.analyzer = new SeniorDeveloperAnalyzer(this, () => this.aiClient);
    this.taskCreator = new SeniorDeveloperTaskCreator(this);
    this.burstMgr = new SeniorDeveloperBurstManager(this, this.analyzer, this.taskCreator);
  }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  async run() {
    await this.checkRateLimit();
    const all = await this.getAllowedRepositories(), repos = this.selectDaily(all);
    if (!repos.length) return { status: "skipped", reason: "empty_allowlist" };
    await this.telegram.sendMessage(`🔧 <b>SENIOR DEVELOPER</b>\n──────────────────────\n🚀 Iniciando análise de <code>${repos.length}</code>/<code>${all.length}</code> repositório(s)...`, "HTML");
    const results = await this.processRepositories(repos);
    results.daily_limit = repos.length; results.total_repositories = all.length;
    results.burst_tasks = (process.env.SENIOR_DEVELOPER_ENABLE_BURST ?? "false").toLowerCase() === "true" ? await this.burstMgr.runBurst(repos) : [];
    await this.sendSummary(results);
    return results;
  }

  /** Each run is bounded to the oldest-updated repositories first. */
  selectDaily(repos: string[]): string[] {
    const limit = parseInt(process.env.SENIOR_DEVELOPER_DAILY_REPO_LIMIT ?? "5", 10);
    return limit > 0 ? repos.slice(0, limit) : [];
  }

  private async sendSummary(r: Record<string, any>) {
    const n = (k: string) => (r[k] ?? []).length, total = TASK_KEYS.reduce((s, k) => s + n(k), 0), failed = n("failed");
    const lines = ["🔧 <b>SENIOR DEVELOPER — RESUMO</b>", "──────────────────────", `📋 <b>Total de tarefas criadas:</b> <code>${total}</code>`,
      `🔒 Security: <code>${n("security_tasks")}</code>  ⚙️ CI/CD: <code>${n("cicd_tasks")}</code>  🚀 Feature: <code>${n("feature_tasks")}</code>`,
      `🧹 Tech Debt: <code>${n("tech_debt_tasks")}</code>  🆕 Modern.: <code>${n("modernization_tasks")}</code>  ⚡ Perf.: <code>${n("performance_tasks")}</code>`];
    if (failed) lines.push(`❌ <b>Falhas:</b> <code>${failed}</code>`);
    const prs: [string, string][] = [];
    for (const k of TASK_KEYS) for (const it of r[k] ?? []) if (it.opencode?.pr_url) prs.push([it.repository ?? "?", it.opencode.pr_url]);
    if (prs.length) { lines.push("──────────────────────", "🔗 <b>PRs abertas:</b>"); for (const [repo, url] of prs.slice(0, 8)) lines.push(`  └ <a href="${url}">${TelegramNotifier.escapeHtml(repo)}</a>`); }
    await this.telegram.sendMessage(lines.join("\n"), "HTML");
  }

  private async processRepositories(repos: string[]): Promise<Record<string, any>> {
    const results: Record<string, any> = { feature_tasks: [], security_tasks: [], cicd_tasks: [], tech_debt_tasks: [], modernization_tasks: [], performance_tasks: [], failed: [], timestamp: new Date().toISOString() };
    for (let i = 0; i < repos.length; i++) {
      const repo = repos[i];
      try {
        this.log(`[${i + 1}/${repos.length}] Analyzing repository: ${repo}`);
        await this.analyzeAndTask(repo, results);
        if (i < repos.length - 1) await sleep(Number(process.env.SENIOR_DEVELOPER_REPO_DELAY_MS ?? 1000));
      } catch (e: any) {
        this.log(`Failed to process ${repo}: ${e?.message ?? e}`, "ERROR"); results.failed.push({ repository: repo, error: String(e?.message ?? e) });
        await this.telegram.sendMessage(`❌ <b>SENIOR DEVELOPER — ERRO</b>\n──────────────────────\n📦 <b>Repo:</b> <code>${repo}</code>\n<pre>Verifique os logs para detalhes.</pre>`, "HTML");
      }
    }
    return results;
  }

  private async analyzeAndTask(repo: string, results: Record<string, any>) {
    for (const [analyze, create, key, flag] of ANALYSIS_METHODS) {
      const analysis = await this.analyzer[analyze](repo);
      if (analysis[flag]) results[key].push({ repository: repo, opencode: await this.taskCreator[create](repo, analysis) });
    }
  }
}
