/** CI Health Agent - monitors failing CI runs, notifies Telegram and opens remediation PRs (public repos only). */
import { BaseAgent } from "../base-agent.ts";
import type { AgentOpts } from "../agent-types.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

export type Failure = { repo: string; name: string; branch: string; url: string; conclusion: string };

export async function remediatePipeline(agent: BaseAgent, repo: any, failures: Failure[]): Promise<Record<string, any> | null> {
  const text = failures.map((f) => `- ${f.name} (${f.conclusion}): ${f.url}`).join("\n");
  const instructions = `Repository: ${repo.full_name}\nTask: Fix failing GitHub Actions workflows detected in the last 24h.\nFailures:\n${text}\n\nRequired process:\n- Apply minimal safe fixes in workflow/config/code related to these failures.\n- Ensure files are valid and consistent.\n- Commit, push, and open a pull request from vibe-code.`;
  try {
    const r = await agent.createOpencodeTask(repo.full_name, instructions, "Fix GitHub Actions failures");
    if (r.status === "task_created") return { repository: repo.full_name, status: "task_created", task_id: r.task_id, task_url: r.task_url };
    return { repository: repo.full_name, status: r.status ?? "failed", error: r.error ?? r.stderr };
  } catch (e: any) { agent.log(`Failed opencode remediation in ${repo.full_name}: ${e?.message ?? e}`, "WARNING"); return null; }
}

export class CIHealthAgent extends BaseAgent {
  constructor(o: AgentOpts) { super("ci_health", { ...o, enforceRepositoryAllowlist: false }); }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  async run() {
    await this.checkRateLimit();
    const cutoff = Date.now() - 24 * 3600_000;
    const failing: Failure[] = [], byRepo = new Map<string, { repo: any; failures: Failure[] }>();
    for (const name of await this.getAllowedRepositories()) {
      try {
        const repo = await this.githubClient.getRepo(name);
        for (const run of await this.githubClient.getWorkflowRuns(name, { status: "completed", limit: 30 })) {
          if (Date.parse(run.created_at) < cutoff) break;
          if (["failure", "timed_out", "action_required"].includes(run.conclusion)) {
            const f: Failure = { repo: repo.full_name, name: run.name || "workflow", branch: run.head_branch || "unknown", url: run.html_url, conclusion: run.conclusion };
            failing.push(f);
            (byRepo.get(name) ?? byRepo.set(name, { repo, failures: [] }).get(name)!).failures.push(f);
          }
        }
      } catch (e: any) { this.log(`Failed to inspect CI for ${name}: ${e?.message ?? e}`, "WARNING"); }
    }
    const fixActions: Record<string, any>[] = [];
    for (const [name, entry] of byRepo) {
      if ((entry.repo.private ?? true) || !entry.failures.length) continue;
      try { const a = await remediatePipeline(this, entry.repo, entry.failures); if (a) fixActions.push(a); }
      catch (e: any) { this.log(`Failed remediation for ${name}: ${e?.message ?? e}`, "WARNING"); }
    }
    await this.sendSummary(failing, fixActions);
    return { agent: "ci-health", owner: this.targetOwner, failures: failing, fix_actions: fixActions, count: failing.length };
  }

  private async sendSummary(failing: Failure[], fixActions: Record<string, any>[]) {
    const esc = TelegramNotifier.escapeHtml;
    const lines = ["🧪 <b>CI HEALTH AGENT</b>", `📅 <code>${esc(new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC")}</code>`, `👤 <b>Owner:</b> <code>${esc(this.targetOwner)}</code>`, "──────────────────────", `❗ <b>Falhas nas últimas 24h:</b> <code>${failing.length}</code>`];
    for (const it of failing.slice(0, 15)) lines.push(`${it.conclusion === "timed_out" ? "⏱️" : "❌"} <a href="${esc(it.url)}">${esc(it.repo)}</a> — <i>${esc(it.name)}</i> [${esc(it.branch)}]`);
    if (fixActions.length) {
      lines.push("──────────────────────", "🔧 <b>Ações de correção iniciadas:</b>");
      for (const a of fixActions.slice(0, 10)) {
        if (a.task_url) lines.push(`  └ <code>${esc(a.repository)}</code>: <a href="${esc(a.task_url)}">task vibe-code</a>`);
        else if (a.status) lines.push(`  └ <code>${esc(a.repository)}</code>: <i>${esc(a.status)}</i>`);
      }
    }
    await this.telegram.sendMessage(lines.join("\n"), "HTML");
  }
}
