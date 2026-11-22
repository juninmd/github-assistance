/** Intelligence Standardizer - enforces AGENTS.md and .agents structure. */
import { BaseAgent } from "../base-agent.ts";
import type { AgentOpts } from "../agent-types.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

const CHECKS: Record<string, string> = {
  missing_agents_md: "AGENTS.md", missing_agents_dir: ".agents", missing_standard_workflow: ".github/workflows/standard.yml",
  missing_contributing: "CONTRIBUTING.md", missing_license: "LICENSE",
};

export class IntelligenceStandardizerAgent extends BaseAgent {
  constructor(o: AgentOpts) { super("intelligence_standardizer", { ...o, enforceRepositoryAllowlist: true }); }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  async run() {
    this.log("Starting Intelligence Standardizer workflow");
    const repos = await this.githubClient.getUserRepos({ sort: "updated", limit: 10 });
    const results: { processed: any[]; skipped: any[]; failed: any[] } = { processed: [], skipped: [], failed: [] };
    for (const repo of repos) {
      try { await this.processRepository(repo, results); }
      catch (e: any) { this.log(`Failed to process ${repo.full_name}: ${e?.message ?? e}`, "ERROR"); results.failed.push({ repository: repo.full_name, error: String(e?.message ?? e) }); }
    }
    await this.sendSummary(results);
    return results;
  }

  async analyzeIntelligence(repo: any): Promise<Record<string, boolean>> {
    const out: Record<string, boolean> = {};
    for (const [key, path] of Object.entries(CHECKS)) {
      try { out[key] = !(await this.githubClient.pathExists(repo.full_name, path)); }
      catch (e: any) { this.log(`Error checking ${path} in ${repo.full_name}: ${e?.message ?? e}`, "WARNING"); out[key] = true; }
    }
    return out;
  }

  private async processRepository(repo: any, results: { processed: any[]; skipped: any[] }) {
    const name = repo.full_name;
    this.log(`Checking intelligence structure for ${name}`);
    const a = await this.analyzeIntelligence(repo);
    if (!a.missing_agents_md && !a.missing_agents_dir && !a.missing_contributing && !a.missing_license) {
      this.log(`Repository ${name} is already standardized.`); results.skipped.push({ repository: name, reason: "already_standardized" }); return;
    }
    const instructions = this.loadTaskInstructions("task-instructions.md", { repository_name: name, ...a });
    const oc = await this.runOpencodeOnRepo(name, instructions, `Standardize ${repo.name} Quality & Intelligence`);
    results.processed.push({ repository: name, pr_url: oc.pr_url, ...a });
  }

  private async sendSummary(r: { processed: any[]; skipped: any[]; failed: any[] }) {
    const esc = TelegramNotifier.escapeHtml;
    const lines = ["🧠 <b>INTELLIGENCE STANDARDIZER</b>", "──────────────────────", `✅ <b>Padronizados:</b> <code>${r.processed.length}</code>`, `⏭️ <b>Pulados:</b> <code>${r.skipped.length}</code>  ❌ <b>Falhas:</b> <code>${r.failed.length}</code>`];
    for (const it of r.processed.slice(0, 5)) {
      lines.push(`  └ <a href="${esc(it.pr_url || `https://github.com/${it.repository}`)}">${esc(it.repository)}</a> — opencode`);
    }
    await this.telegram.sendMessage(lines.join("\n"), "HTML");
  }
}
