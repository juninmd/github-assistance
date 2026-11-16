/** Product Manager - roadmap planning and feature prioritization. */
import { BaseAgent } from "../base-agent.ts";
import { makeAi, type AgentOpts } from "../agent-types.ts";
import { RoadmapGenerator } from "./roadmap-generator.ts";
import type { AIClient } from "../../ai/client.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

export async function analyzeIssuesWithAi(ai: { generate(p: string): Promise<string> }, issues: any[], description: string): Promise<{ ai_summary: string }> {
  if (!issues.length) return { ai_summary: "No issues to analyze." };
  const text = issues.slice(0, 20).map((i) => `- #${i.number} ${i.title} (Labels: ${(i.labels ?? []).map((l: any) => l.name).join(", ")})`).join("\n");
  const prompt = `\n    Analyze the following repository and its top open issues to provide a strategic product summary.\n\n    Repository Description: ${description}\n\n    Top Issues:\n    ${text}\n\n    Provide a concise summary of the current state of the repository, highlighting key areas of focus, recurring themes, and strategic recommendations for the product roadmap.\n    `;
  try { return { ai_summary: await ai.generate(prompt) }; } catch (e: any) { return { ai_summary: `Failed to generate AI summary: ${e?.message ?? e}` }; }
}

export class ProductManagerAgent extends BaseAgent {
  private _ai: AIClient | null = null; private roadmapGen: RoadmapGenerator;
  constructor(o: AgentOpts) {
    super("product_manager", { ...o, enforceRepositoryAllowlist: true });
    this._ai = o.aiClient ?? makeAi({ ...o.ai, provider: o.ai?.provider ?? "gemini" }).client;
    this.roadmapGen = new RoadmapGenerator(this, () => this._ai);
  }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  async run() {
    this.log("Starting Product Manager workflow");
    const repos = await this.getAllowedRepositories();
    if (!repos.length) return { status: "skipped", reason: "empty_allowlist" };
    const results: { processed: any[]; failed: any[]; timestamp: string } = { processed: [], failed: [], timestamp: new Date().toISOString() };
    for (const repo of repos) {
      try { this.log(`Analyzing repository: ${repo}`); results.processed.push({ repository: repo, roadmap: await this.analyzeAndCreateRoadmap(repo) }); }
      catch (e: any) { this.log(`Failed to process ${repo}: ${e?.message ?? e}`, "ERROR"); results.failed.push({ repository: repo, error: String(e?.message ?? e) }); }
    }
    await this.sendSummary(results);
    return results;
  }

  private async sendSummary(r: { processed: any[]; failed: any[] }) {
    const esc = TelegramNotifier.escapeHtml;
    const lines = ["📋 <b>PRODUCT MANAGER</b>", "──────────────────────", `📦 <b>Roadmaps processados:</b> <code>${r.processed.length}</code>`, `❌ <b>Falhas:</b> <code>${r.failed.length}</code>`];
    for (const it of r.processed.slice(0, 5)) {
      const rm = it.roadmap ?? {};
      if (rm.skipped) lines.push(`  └ <code>${esc(it.repository)}</code> — <i>${esc(rm.reason ?? "skipped")}</i>`);
      else if (rm.pr_url) lines.push(`  └ <a href="${esc(rm.pr_url)}">${esc(it.repository)}</a> — opencode`);
      else lines.push(`  └ <code>${esc(it.repository)}</code> — jules`);
    }
    await this.telegram.sendMessage(lines.join("\n"), "HTML");
  }

  async analyzeAndCreateRoadmap(repository: string): Promise<Record<string, any>> {
    const info = await this.getRepositoryInfo(repository);
    if (!info) throw new Error(`Could not access repository ${repository}`);
    if (await this.roadmapGen.isRoadmapUpToDate(info)) return { repository, skipped: true, reason: "roadmap_up_to_date" };
    const analysis = await this.roadmapGen.analyzeRepository(info);
    const instructions = this.roadmapGen.generateInstructions(repository, analysis);
    const extra = { analysis_summary: analysis.summary ?? "", priority_count: (analysis.priorities ?? []).length };
    if (await this.hasRecentJulesSession(repository, "roadmap")) {
      this.log(`Jules session exists for ${repository}. Using opencode fallback.`);
      const oc = await this.runOpencodeOnRepo(repository, instructions, `Update Product Roadmap for ${info.name}`);
      return { repository, via_opencode: true, pr_url: oc.pr_url, ...extra };
    }
    const s = await this.createJulesSession(repository, instructions, `Update Product Roadmap for ${repository}`, { baseBranch: info.default_branch ?? "main" });
    return { repository, session_id: s.id, via_opencode: false, ...extra };
  }
}
