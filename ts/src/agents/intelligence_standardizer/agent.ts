/** Intelligence Standardizer (repo-standards stage) - enforces AGENTS.md and .agents structure in every active repository. */
import { BaseAgent } from "../base-agent.ts";
import { mapLimit } from "../core/utils.ts";
import type { AgentOpts } from "../agent-types.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

const CHECKS: Record<string, string> = {
  missing_agents_md: "AGENTS.md", missing_agents_dir: ".agents", missing_standard_workflow: ".github/workflows/standard.yml",
  missing_contributing: "CONTRIBUTING.md", missing_license: "LICENSE",
};

const TITLE_PREFIX = "Standardize ";
const maxPrs = () => Math.max(0, parseInt(process.env.REPO_STANDARDS_MAX_PRS ?? "", 10) || 5);

export class IntelligenceStandardizerAgent extends BaseAgent {
  constructor(o: AgentOpts) { super("intelligence_standardizer", { ...o, enforceRepositoryAllowlist: true }); }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  /** Every active repository of the owner: the merge gate needs AGENTS.md everywhere, not only in recent repos. */
  async run() {
    this.log("Starting Intelligence Standardizer workflow");
    const owner = this.targetOwner.toLowerCase();
    const repos = (await this.githubClient.getUserRepos({ sort: "updated", limit: null }))
      .filter((r) => !r.archived && !r.fork && (r.owner?.login ?? owner).toLowerCase() === owner);
    const results: { processed: any[]; skipped: any[]; failed: any[] } = { processed: [], skipped: [], failed: [] };
    const analyzed = await mapLimit(repos, 8, async (repo) => {
      try { return { repo, a: await this.analyzeIntelligence(repo) }; }
      catch (e: any) { results.failed.push({ repository: repo.full_name, error: String(e?.message ?? e) }); return null; }
    });
    // Missing AGENTS.md first: without it the PR Assistant blocks every merge in that repository.
    const todo = analyzed.filter((x): x is { repo: any; a: Record<string, boolean> } => x !== null)
      .sort((x, y) => Number(y.a.missing_agents_md) - Number(x.a.missing_agents_md));
    let opened = 0;
    for (const { repo, a } of todo) {
      try {
        if (opened >= maxPrs() && this.needsWork(a)) { results.skipped.push({ repository: repo.full_name, reason: "run_cap_reached" }); continue; }
        if (await this.processRepository(repo, a, results)) opened++;
      } catch (e: any) { this.log(`Failed to process ${repo.full_name}: ${e?.message ?? e}`, "ERROR"); results.failed.push({ repository: repo.full_name, error: String(e?.message ?? e) }); }
    }
    await this.sendSummary(results);
    return results;
  }

  needsWork = (a: Record<string, boolean>) => a.missing_agents_md || a.missing_agents_dir || a.missing_contributing || a.missing_license;

  /** An open standardization PR means the work is already waiting for review: never open a second one. */
  private async hasOpenPr(name: string): Promise<boolean> {
    try { return (await this.githubClient.getPulls(name, { state: "open" })).some((p) => (p.title ?? "").includes(TITLE_PREFIX)); }
    catch { return false; }
  }

  async analyzeIntelligence(repo: any): Promise<Record<string, boolean>> {
    const out: Record<string, boolean> = {};
    for (const [key, path] of Object.entries(CHECKS)) {
      try { out[key] = !(await this.githubClient.pathExists(repo.full_name, path)); }
      catch (e: any) { this.log(`Error checking ${path} in ${repo.full_name}: ${e?.message ?? e}`, "WARNING"); out[key] = true; }
    }
    return out;
  }

  private async processRepository(repo: any, a: Record<string, boolean>, results: { processed: any[]; skipped: any[] }): Promise<boolean> {
    const name = repo.full_name;
    if (!this.needsWork(a)) {
      this.log(`Repository ${name} is already standardized.`); results.skipped.push({ repository: name, reason: "already_standardized" }); return false;
    }
    if (await this.hasOpenPr(name)) { results.skipped.push({ repository: name, reason: "pr_already_open" }); return false; }
    const instructions = this.loadTaskInstructions("task-instructions.md", { repository_name: name, ...a });
    const oc = await this.runOpencodeOnRepo(name, instructions, `${TITLE_PREFIX}${repo.name} Quality & Intelligence`);
    results.processed.push({ repository: name, pr_url: oc.pr_url, ...a });
    return true;
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
