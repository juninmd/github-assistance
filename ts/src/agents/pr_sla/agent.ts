/** PR SLA Agent - alerts on stale pull requests and auto-nudges reviewers. */
import { BaseAgent } from "../base-agent.ts";
import type { AgentOpts } from "../agent-types.ts";
import { buildOriginMetadata, mapLimit } from "../core/utils.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

const nudgeComment = (hours: number) =>
  `⏱️ **SLA Alert — revisão pendente**\n\nEste pull request está sem atualização há **${hours}h** e ultrapassou o SLA de 24h.\n\nPor favor, um dos revisores avalie ou deixe um comentário com o status.\n\n${buildOriginMetadata("pr_sla", "N/A (regra determinística)")}`;

export class PRSLAAgent extends BaseAgent {
  constructor(o: AgentOpts) { super("pr_sla", o); }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  async run() {
    const threshold = Date.now() - 24 * 3600_000;
    const issues = await this.githubClient.searchPrs(`is:pr is:open archived:false user:${this.targetOwner}`);
    const stale: Record<string, string>[] = [], nudged: string[] = [];
    const resolved = await mapLimit(issues, 8, async (issue) => {
      try { return await this.githubClient.getPrFromIssue(issue); }
      catch (e: any) { this.log(`Failed to inspect PR SLA: ${e?.message ?? e}`, "WARNING"); return null; }
    });
    for (const pr of resolved) {
      if (!pr) continue;
      try {
        const last = Date.parse(pr.updated_at ?? pr.created_at);
        if (last < threshold) {
          const hours = Math.floor((Date.now() - last) / 3600_000);
          stale.push({ repo: pr.base.repo.full_name, number: String(pr.number), title: pr.title, url: pr.html_url, hours_without_update: String(hours) });
          const url = await this.nudge(pr, hours);
          if (url) nudged.push(url);
        }
      } catch (e: any) { this.log(`Failed to inspect PR SLA: ${e?.message ?? e}`, "WARNING"); }
    }
    await this.sendSummary(stale, nudged);
    return { agent: "pr-sla", owner: this.targetOwner, stale_pull_requests: stale, count: stale.length, nudged };
  }

  private async nudge(pr: any, hours: number): Promise<string | null> {
    try {
      const comments = await this.githubClient.getIssueComments(pr.base.repo.full_name, pr.number);
      if (comments.slice(-5).some((c: any) => (c.body ?? "").includes("SLA Alert") && (c.body ?? "").includes("github-assistance"))) return null;
      const c = await this.githubClient.commentOnPr(pr, nudgeComment(hours));
      this.log(`Nudged PR #${pr.number} in ${pr.base.repo.full_name} (${hours}h stale)`);
      return c.html_url;
    } catch (e: any) { this.log(`Failed to nudge PR #${pr.number}: ${e?.message ?? e}`, "WARNING"); return null; }
  }

  private async sendSummary(stale: Record<string, string>[], nudged: string[]) {
    const esc = TelegramNotifier.escapeHtml;
    const lines = ["⏱️ <b>PR SLA AGENT</b>", `📅 <code>${esc(new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC")}</code>`, `👤 <b>Owner:</b> <code>${esc(this.targetOwner)}</code>`, "──────────────────────",
      `🕒 <b>PRs sem atualização (&gt;24h):</b> <code>${stale.length}</code>`, `💬 <b>Nudges enviados:</b> <code>${nudged.length}</code>`];
    for (const it of stale.slice(0, 20)) lines.push(`${Number(it.hours_without_update) >= 72 ? "🔴" : "🟡"} <a href="${esc(it.url)}">${esc(it.repo)} #${it.number}</a> — <b>${esc(it.hours_without_update)}h</b> — <i>${esc(it.title)}</i>`);
    await this.telegram.sendMessage(lines.join("\n"), "HTML");
  }
}
