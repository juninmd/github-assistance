/** End-of-day burst of opencode tasks. */
import type { BaseAgent } from "../base-agent.ts";
import type { SeniorDeveloperAnalyzer } from "./analyzers.ts";
import type { SeniorDeveloperTaskCreator } from "./task-creator.ts";

const envInt = (n: string, d: number) => { const v = parseInt(process.env[n] ?? "", 10); return Number.isNaN(v) ? d : v; };
const nowMinus3 = () => new Date(Date.now() - 3 * 3600_000);

export class SeniorDeveloperBurstManager {
  constructor(private agent: BaseAgent, private analyzer: SeniorDeveloperAnalyzer, private creator: SeniorDeveloperTaskCreator) {}

  async runBurst(repos: string[]): Promise<Record<string, any>[]> {
    const max = envInt("SENIOR_DEVELOPER_BURST_MAX_ACTIONS", 0), trigger = envInt("SENIOR_DEVELOPER_BURST_TRIGGER_HOUR_UTC_MINUS_3", 18);
    if (max <= 0 || nowMinus3().getUTCHours() < trigger || !repos.length) return [];
    const toRun = max;
    const out: Record<string, any>[] = [];
    for (let i = 0; i < toRun; i++) out.push(await this.execute(repos, i));
    return out;
  }

  private async execute(repos: string[], idx: number) {
    const repo = repos[idx % repos.length];
    try { return await this.createBurstTask(repo, idx); } catch (e: any) { return { repository: repo, action: idx + 1, error: String(e?.message ?? e) }; }
  }

  private async createBurstTask(repo: string, idx: number) {
    const a = this.analyzer, c = this.creator;
    const methods = [
      [a.analyzeSecurity, c.createSecurityTask, "needs_attention", "create_security_task"], [a.analyzeCicd, c.createCicdTask, "needs_improvement", "create_cicd_task"],
      [a.analyzeTechDebt, c.createTechDebtTask, "needs_attention", "create_tech_debt_task"], [a.analyzeModernization, c.createModernizationTask, "needs_modernization", "create_modernization_task"],
      [a.analyzePerformance, c.createPerformanceTask, "needs_optimization", "create_performance_task"], [a.analyzeRoadmapFeatures, c.createFeatureImplementationTask, "has_features", "create_feature_implementation_task"],
    ] as const;
    const [analyze, create, flag, name] = methods[idx % methods.length];
    const analysis = await analyze.call(a, repo);
    if (!analysis[flag]) return { repository: repo, action: idx + 1, skipped: true, reason: "no_findings" };
    return { repository: repo, action: idx + 1, opencode: await create.call(c, repo, analysis), task_type: name };
  }
}
