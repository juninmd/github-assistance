/** Security Scanner - scans repositories for exposed secrets (gitleaks) and prohibited cron workflows. */
import { BaseAgent } from "../base-agent.ts";
import { mapLimit } from "../core/utils.ts";
import type { AgentOpts } from "../agent-types.ts";
import * as scanner from "./scanner.ts";
import { buildAndSendReport, sendErrorNotification } from "./telegram-summary.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

export class SecurityScannerAgent extends BaseAgent {
  private authorCache = new Map<string, string>();
  constructor(o: AgentOpts) { super("security_scanner", { ...o, enforceRepositoryAllowlist: false }); }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  // Instance wrappers so tests can stub them.
  ensureGitleaksInstalled() { return scanner.ensureGitleaksInstalled(this.log); }
  scanRepository(repo: string, branch = "main") { return scanner.scanRepository(repo, branch, this.log); }

  async run() {
    this.log("Starting Security Scanner workflow"); this.log(`Target owner: ${this.targetOwner}`);
    const results: Record<string, any> = { total_repositories: 0, scanned: 0, failed: 0, total_findings: 0, total_cron_workflows: 0, all_repositories: [], repositories_with_findings: [], repositories_with_cron: [], scan_errors: [], timestamp: new Date().toISOString() };
    if (!(await this.ensureGitleaksInstalled())) {
      const msg = "Failed to install gitleaks. Cannot proceed with security scan.";
      this.log(msg, "ERROR"); results.error = msg; await sendErrorNotification(this.telegram, this.targetOwner, msg); return results;
    }
    const repos = await this.getAllRepositories();
    results.total_repositories = repos.length; results.all_repositories = repos;
    if (!repos.length) { this.log("No repositories found to scan"); await this.notify(results); return results; }
    for (const { name, default_branch } of repos) {
      try {
        const s = await this.scanRepository(name, default_branch);
        if (s.scanned) {
          results.scanned++;
          if (s.findings.length) { results.total_findings += s.findings.length; results.repositories_with_findings.push({ repository: name, default_branch, findings: s.findings }); }
          if (s.cron_workflows?.length) { results.total_cron_workflows += s.cron_workflows.length; results.repositories_with_cron.push({ repository: name, default_branch, cron_workflows: s.cron_workflows }); }
        } else { results.failed++; if (s.error) results.scan_errors.push({ repository: name, error: s.error }); }
      } catch (e: any) {
        this.log(`Unexpected error scanning ${name}: ${e?.message ?? e}`, "ERROR"); results.failed++; results.scan_errors.push({ repository: name, error: String(e?.message ?? e) });
        await this.telegram.sendMessage(`❌ <b>SECURITY SCANNER — ERRO SCAN</b>\n📦 <code>${TelegramNotifier.escapeHtml(name)}</code>\n<pre>Verifique os logs para detalhes.</pre>`, "HTML");
      }
    }
    this.log(`Scan completed: ${results.scanned} scanned, ${results.failed} failed, ${results.total_findings} findings, ${results.total_cron_workflows} prohibited cron workflow(s)`);
    await this.notify(results);
    return results;
  }

  private async getAllRepositories(): Promise<{ name: string; default_branch: string }[]> {
    try {
      const found = await mapLimit(await this.getAllowedRepositories(), 8, async (name) => {
        try { return { name, default_branch: (await this.githubClient.getRepo(name)).default_branch }; }
        catch (e: any) { this.log(`Error fetching repo ${name}: ${e?.message ?? e}`, "WARNING"); return null; }
      });
      const out = found.filter((r): r is { name: string; default_branch: string } => r !== null);
      this.log(`Found ${out.length} repositories to scan for ${this.targetOwner}`);
      return out;
    } catch (e: any) { this.log(`Error fetching repositories: ${e?.message ?? e}`, "ERROR"); return []; }
  }

  async getCommitAuthor(repo: string, sha: string): Promise<string> {
    if (!sha) return "unknown";
    if (!this.canWorkOnRepository(repo)) { this.log(`Commit author lookup denied by owner scope: ${repo}`, "WARNING"); return "unknown"; }
    const key = `${repo}:${sha}`, hit = this.authorCache.get(key);
    if (hit) return hit;
    let login = "unknown";
    try { login = (await this.githubClient.get(`/repos/${repo}/commits/${sha}`)).author?.login || "unknown"; }
    catch (e: any) { this.log(`Error fetching commit author for ${sha}: ${e?.message ?? e}`, "WARNING"); }
    this.authorCache.set(key, login);
    return login;
  }

  private notify(r: Record<string, any>) { return buildAndSendReport(r, this.telegram, this.targetOwner, (repo, sha) => this.getCommitAuthor(repo, sha)); }
}
