/** Dependency Manager - detects ecosystems and delegates safe upgrades to opencode (one grouped PR). */
import { BaseAgent } from "../base-agent.ts";
import type { AgentOpts } from "../agent-types.ts";
import { detectEcosystems, ecosystemSummary, rootFilenames, type Ecosystem } from "./detect.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

export const dependencyDryRun = () => ["1", "true", "yes", "on"].includes((process.env.DEPENDENCY_DRY_RUN ?? "").trim().toLowerCase());

export class DependencyManagerAgent extends BaseAgent {
  constructor(o: AgentOpts) { super("dependency_manager", { ...o, enforceRepositoryAllowlist: true }); }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  async run() {
    await this.checkRateLimit();
    this.log("Starting Dependency Manager workflow");
    const results: { processed: any[]; skipped: any[]; failed: any[] } = { processed: [], skipped: [], failed: [] };
    for (const name of await this.getAllowedRepositories()) {
      try { await this.processRepository(name, results); }
      catch (e: any) { this.log(`Failed to process ${name}: ${e?.message ?? e}`, "ERROR"); results.failed.push({ repository: name, error: String(e?.message ?? e) }); }
    }
    await this.sendSummary(results);
    return results;
  }

  private async processRepository(name: string, results: { processed: any[]; skipped: any[] }) {
    const repo = await this.githubClient.getRepo(name);
    const ecos = await this.detect(repo);
    if (!ecos.length) { this.log(`No dependencies detected in ${name}`); results.skipped.push({ repository: name, reason: "no_dependencies" }); return; }
    const names = ecos.map((e) => e.name);
    if (dependencyDryRun()) {
      this.log(`[DRY-RUN] ${name}: would update dependencies (${names.join(", ")})`);
      results.processed.push({ repository: name, ecosystems: names, pr_url: null, status: "dry_run" }); return;
    }
    this.log(`${name}: updating dependencies (${names.join(", ")})`);
    const r = await this.createOpencodeTask(name, DependencyManagerAgent.buildInstructions(ecos), `Update dependencies for ${repo.name}`, repo.default_branch);
    results.processed.push({ repository: name, ecosystems: names, pr_url: r.task_url, status: r.status });
  }

  private async detect(repo: any): Promise<Ecosystem[]> {
    try { return detectEcosystems(rootFilenames(await this.githubClient.getTreePaths(repo.full_name, repo.default_branch))); }
    catch (e: any) { this.log(`Could not read tree for ${repo.full_name}: ${e?.message ?? e}`, "WARNING"); return []; }
  }

  static buildInstructions(ecos: Ecosystem[]): string {
    return ["Atualize as dependências deste repositório com segurança, priorizando correções de segurança. Use a IA (opencode) para decidir e aplicar.", "", "Ecossistemas detectados:",
      ...ecos.map((e) => `- ${ecosystemSummary(e)} | auditoria: ${e.auditHint} | desatualizadas: ${e.outdatedHint}`), "", "Regras:",
      "1. Segurança primeiro: rode a auditoria e corrija vulnerabilidades (CVE) antes de qualquer bump não essencial.",
      "2. Liste o que está desatualizado e aplique bumps de patch/minor.",
      "3. NÃO aplique majors sem checar breaking changes; se houver, deixe documentado e fora deste PR.",
      "4. Atualize o lockfile e rode a suíte de testes; corrija o que quebrar.",
      "5. Mudanças mínimas e verificáveis; não refatore código não relacionado.", "",
      "Abra UM pull request agrupado, com resumo no corpo: dependências atualizadas, CVEs corrigidas e breaking changes evitadas."].join("\n");
  }

  private async sendSummary(r: { processed: any[]; skipped: any[]; failed: any[] }) {
    const esc = TelegramNotifier.escapeHtml;
    const lines = ["📦 <b>DEPENDENCY MANAGER AGENT</b>", "──────────────────────", `✅ <b>PRs abertos:</b> <code>${r.processed.length}</code>`, `⏭️ <b>Pulados:</b> <code>${r.skipped.length}</code>  ❌ <b>Falhas:</b> <code>${r.failed.length}</code>`];
    for (const it of r.processed.slice(0, 5)) {
      const ecos = esc((it.ecosystems ?? []).join(", "));
      lines.push(it.pr_url ? `  └ <a href="${esc(it.pr_url)}">${esc(it.repository)}</a> (${ecos})` : `  └ <code>${esc(it.repository)}</code> (${ecos})`);
    }
    await this.telegram.sendMessage(lines.join("\n"), "HTML");
  }
}
