/** Readme Curator - refreshes missing, stale (>6 months) or weak READMEs via opencode PRs. */
import { BaseAgent } from "../base-agent.ts";
import { mapLimit } from "../core/utils.ts";
import type { AgentOpts } from "../agent-types.ts";
import { DEFAULT_MIN_SCORE, needsWork, scoreReadme } from "./scoring.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

export const DEFAULT_MAX_AGE_DAYS = 180;
const envInt = (n: string, d: number) => { const v = parseInt(process.env[n] || "", 10); return Number.isNaN(v) ? d : v; };

export class ReadmeCuratorAgent extends BaseAgent {
  private dates = new Map<string, number>();
  constructor(o: AgentOpts) { super("readme_curator", { ...o, enforceRepositoryAllowlist: false }); }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  async run() {
    await this.checkRateLimit();
    this.log("Starting Readme Curator workflow");
    const results: { processed: any[]; skipped: any[]; failed: any[] } = { processed: [], skipped: [], failed: [] };
    const repos: [number, any][] = [];
    const prepared = await mapLimit(await this.getAllowedRepositories(), 8, async (name) => {
      try { const repo = await this.githubClient.getRepo(name); return { ok: [await this.readmeLastModified(repo), repo] as [number, any] }; }
      catch (e: any) { this.log(`Failed to process ${name}: ${e?.message ?? e}`, "ERROR"); return { fail: { repository: name, error: String(e?.message ?? e) } }; }
    });
    for (const p of prepared) { if (p.ok) repos.push(p.ok); else results.failed.push(p.fail); }
    repos.sort((a, b) => (a[0] === b[0] ? 0 : a[0] < b[0] ? -1 : 1)); // oldest first; missing READMEs lead
    for (const [, repo] of repos) {
      try { await this.processRepository(repo, results); }
      catch (e: any) { this.log(`Failed to process ${repo.full_name}: ${e?.message ?? e}`, "ERROR"); results.failed.push({ repository: repo.full_name, error: String(e?.message ?? e) }); }
    }
    await this.sendSummary(results);
    return results;
  }

  private async processRepository(repo: any, results: { processed: any[]; skipped: any[] }) {
    const name = repo.full_name;
    if (repo.archived || repo.fork) { results.skipped.push({ repository: name, reason: "archived_or_fork" }); return; }
    this.log(`Checking README quality for ${name}`);
    let needs: boolean, reason: string;
    try {
      const readme = await this.githubClient.getReadme(name);
      if (!readme) { needs = true; reason = "missing"; }
      else { [needs, reason] = this.needsImprovement(readme.content); if (!needs) [needs, reason] = await this.isStale(repo); }
    } catch (e: any) { this.log(`Error checking README in ${name}: ${e?.message ?? e}`, "WARNING"); needs = true; reason = `error: ${e?.name ?? "Error"}`; }
    if (!needs) { this.log(`README for ${name} is already high-quality.`); results.skipped.push({ repository: name, reason: "already_good" }); return; }
    this.log(`README in ${name} needs improvement because it is ${reason}`);
    const r = await this.createOpencodeTask(name, ReadmeCuratorAgent.instructions(name, reason), `Improve README.md for ${repo.name}`, repo.default_branch);
    results.processed.push({ repository: name, reason, pr_url: r.task_url, status: r.status });
  }

  static instructions(name: string, reason: string): string {
    return `Repository: ${name}\nTask: Create or significantly improve README.md (current state: ${reason}).\n\nMandatory rubric - make sure ALL items are covered:\n` +
      ["Write the README in English, translating any existing content in another language.", "Title (H1) + short description of what the project does and who it is for (pitch).",
        "Real badges (CI, coverage, version/license) pointing to the correct repo URLs.", "Installation using the package manager detected in the repository.",
        "Copy-pasteable quickstart (code blocks) with an example that actually works.", "Configuration table (environment variables / options), when applicable.",
        "A Mermaid diagram (architecture/flow) and, if possible, a screenshot/GIF.", "Sections: Features, Usage, Configuration, Contributing, License.",
        "Verify every statement against the current code; fix outdated commands, paths and versions.", "Preserve valid badges, links and footers; expand, do not discard valid content.",
        "No generic AI filler ('High Performance', 'Clean Architecture') without evidence.", "In the PR body, include a preview (rendered summary / before-and-after).",
        "Finally, commit/push to a branch and open a pull request."].map((x) => `- ${x}`).join("\n");
  }

  private needsImprovement(content: string): [boolean, string] {
    const s = scoreReadme(content), min = envInt("README_MIN_SCORE", DEFAULT_MIN_SCORE);
    return needsWork(s, min) ? [true, `score ${s.score}/${min} (faltando: ${s.missing.join(", ") || "geral"})`] : [false, ""];
  }

  /** Last README commit time (ms): -Infinity if missing, +Infinity if unknown/archived/fork. */
  async readmeLastModified(repo: any): Promise<number> {
    const name = repo.full_name, hit = this.dates.get(name);
    if (hit !== undefined) return hit;
    if (repo.archived || repo.fork) return Infinity;
    let last: number;
    try {
      const readme = await this.githubClient.getReadme(name);
      if (!readme) last = -Infinity;
      else { const [c] = await this.githubClient.getPathCommits(name, readme.path, 1); last = c ? Date.parse(c.commit.committer.date) : -Infinity; }
    } catch (e: any) { this.log(`Could not read README history for ${name}: ${e?.message ?? e}`, "WARNING"); last = Infinity; }
    this.dates.set(name, last);
    return last;
  }

  private async isStale(repo: any): Promise<[boolean, string]> {
    const max = envInt("README_MAX_AGE_DAYS", DEFAULT_MAX_AGE_DAYS), days = Math.floor((Date.now() - (await this.readmeLastModified(repo))) / 86400_000);
    return days > max ? [true, `stale (last updated ${days} days ago, limit ${max})`] : [false, ""];
  }

  private async sendSummary(r: { processed: any[]; skipped: any[]; failed: any[] }) {
    const esc = TelegramNotifier.escapeHtml;
    const lines = ["📚 <b>README CURATOR AGENT</b>", "──────────────────────", `✅ <b>Atualizados (PRs abertos):</b> <code>${r.processed.length}</code>`, `skip <b>Pulados:</b> <code>${r.skipped.length}</code>  ❌ <b>Falhas:</b> <code>${r.failed.length}</code>`];
    for (const it of r.processed.slice(0, 5)) lines.push(it.pr_url ? `  └ <a href="${esc(it.pr_url)}">${esc(it.repository)}</a> (${esc(it.reason ?? "unknown")})` : `  └ <code>${esc(it.repository)}</code> (${esc(it.reason ?? "unknown")})`);
    await this.telegram.sendMessage(lines.join("\n"), "HTML");
  }
}
