/** Identifies and deletes merged branches across all repositories (never the default, protected or unmerged). */
import { BaseAgent } from "../base-agent.ts";
import type { AgentOpts } from "../agent-types.ts";
import { GithubError } from "../../github/client.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

const esc = TelegramNotifier.escapeHtml;
export class BranchCleanerAgent extends BaseAgent {
  constructor(o: AgentOpts) { super("branch_cleaner", { ...o, enforceRepositoryAllowlist: false }); }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  async run() {
    const repos = await this.getAllowedRepositories();
    const results = { processed_repos: 0, deleted_branches: [] as string[], failed_branches: [] as string[], skipped_repos: [] as string[] };
    this.log(`Starting branch cleaning for ${repos.length} repositories...`);
    for (const name of repos) {
      try {
        const repo = await this.githubClient.getRepo(name);
        if (!repo) {
          this.log(`Repository ${name} not found, skipping.`, "WARNING"); results.skipped_repos.push(name);
          await this.telegram.sendMessage(`⚠️ <b>BRANCH CLEANER — REPO NÃO ENCONTRADO</b>\n📦 <code>${esc(name)}</code>`); continue;
        }
        this.log(`Cleaning repository: ${name}`);
        const def = repo.default_branch; // NEVER DELETE THIS
        this.log(`Default branch for ${name} is '${def}'`);
        let deletedHere = 0;
        for (const b of await this.githubClient.getBranches(name)) {
          if (b.name === def) continue;
          if (b.protected) { this.log(`Skipping protected branch: ${b.name}`); continue; }
          try {
            const cmp = await this.githubClient.compare(name, def, b.name);
            if (cmp.ahead_by === 0) {
              this.log(`Deleting merged branch: ${b.name} from ${name}`);
              await this.githubClient.deleteBranch(name, b.name);
              results.deleted_branches.push(`${name}#${b.name}`); deletedHere++;
            } else this.log(`Branch ${b.name} is NOT merged (ahead by ${cmp.ahead_by}), skipping.`);
          } catch (e) {
            if (!(e instanceof GithubError)) throw e;
            this.log(`Failed to check/delete branch ${b.name}: ${e.message}`, "ERROR");
            results.failed_branches.push(`${name}#${b.name}`);
            await this.telegram.sendMessage(`❌ <b>BRANCH CLEANER — FALHA AO DELETAR</b>\n📦 <code>${esc(name)}</code>  branch: <code>${esc(b.name)}</code>\n<pre>Verifique os logs para detalhes.</pre>`);
          }
        }
        results.processed_repos++;
        if (deletedHere) this.log(`Deleted ${deletedHere} branches from ${name}`);
      } catch (e: any) {
        this.log(`Error processing repository ${name}: ${e?.message ?? e}`, "ERROR"); results.skipped_repos.push(name);
        await this.telegram.sendMessage(`❌ <b>BRANCH CLEANER — ERRO REPO</b>\n📦 <code>${esc(name)}</code>\n<pre>Verifique os logs para detalhes.</pre>`);
      }
    }
    this.log(`Branch cleaning finished. Total deleted: ${results.deleted_branches.length}`);
    const lines = ["🌿 <b>BRANCH CLEANER</b>", "──────────────────────", `🗑️ <b>Branches deletadas:</b> <code>${results.deleted_branches.length}</code>`, `❌ <b>Falhas:</b> <code>${results.failed_branches.length}</code>`, ...results.deleted_branches.slice(0, 10).map((b) => `  └ <code>${esc(b)}</code>`)];
    await this.telegram.sendMessage(lines.join("\n"), "HTML");
    return results;
  }
}
