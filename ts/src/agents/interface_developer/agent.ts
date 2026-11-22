/** Interface Developer - UI/UX opportunities: creates issues and opencode PRs. */
import { BaseAgent } from "../base-agent.ts";
import { makeAi, type AgentOpts } from "../agent-types.ts";
import type { AIClient } from "../../ai/client.ts";
import { assignOwner, buildOriginMetadata, ROADMAP_LABEL } from "../core/utils.ts";
import { DEFAULT_OLLAMA_MODEL } from "../../config/settings.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

const FRONTEND = ["JavaScript", "TypeScript", "Vue", "HTML"], UI_KEYWORDS = ["ui", "ux", "design", "interface", "component", "layout", "style"];

export class InterfaceDeveloperAgent extends BaseAgent {
  private aiOpts: AgentOpts["ai"]; private aiClient: AIClient | null | undefined; aiModel: string;
  constructor(o: AgentOpts) {
    super("interface_developer", o);
    this.aiOpts = o.ai; this.aiClient = o.aiClient; this.aiModel = o.ai?.model ?? DEFAULT_OLLAMA_MODEL;
  }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  private getAi(): AIClient | null {
    if (this.aiClient !== undefined) return this.aiClient;
    try { return (this.aiClient = makeAi(this.aiOpts).client); } catch (e: any) { this.log(`AI client unavailable: ${e?.message ?? e}`, "WARNING"); return (this.aiClient = null); }
  }

  async run() {
    this.log("Starting Interface Developer workflow");
    const repos = await this.getAllowedRepositories();
    if (!repos.length) { this.log("No repositories in allowlist. Nothing to do.", "WARNING"); return { status: "skipped", reason: "empty_allowlist" }; }
    const results: { ui_issues_created: any[]; failed: any[]; timestamp: string } = { ui_issues_created: [], failed: [], timestamp: new Date().toISOString() };
    for (const repo of repos) {
      try {
        this.log(`Analyzing UI needs for: ${repo}`);
        const a = await this.analyzeUiNeeds(repo);
        if (!a.has_ui_work) { this.log(`No UI work needed for ${repo}`); continue; }
        const issue = await this.createUiImprovementIssue(repo, a);
        const entry: Record<string, any> = { repository: repo, issue_url: issue?.issue_url ?? null, improvements: a.improvements };
        if (issue && a.improvements.length) {
          const oc = await this.runOpencodeOnRepo(repo, `Implement the following UI/UX improvements in this repository:\n${a.improvements.map((i: string) => `- ${i}`).join("\n")}\n\nFocus on changes that can be done without breaking existing functionality. Update DESIGN.md if it doesn't exist, add README badges if missing, and apply any straightforward styling improvements.`, "ui: implement UI/UX improvements");
          entry.opencode_pr_url = oc.pr_url;
        }
        results.ui_issues_created.push(entry);
      } catch (e: any) { this.log(`Failed to process ${repo}: ${e?.message ?? e}`, "ERROR"); results.failed.push({ repository: repo, error: String(e?.message ?? e) }); }
    }
    this.log(`Completed: ${results.ui_issues_created.length} UI issues created`);
    await this.sendSummary(results);
    return results;
  }

  private async sendSummary(r: { ui_issues_created: any[]; failed: any[] }) {
    const esc = TelegramNotifier.escapeHtml;
    const lines = ["🎨 <b>INTERFACE DEVELOPER</b>", "──────────────────────", `🖼️ <b>Issues de UI criadas:</b> <code>${r.ui_issues_created.length}</code>`, `❌ <b>Falhas:</b> <code>${r.failed.length}</code>`];
    for (const it of r.ui_issues_created.slice(0, 5)) {
      const parts: string[] = [];
      if (it.issue_url) parts.push(`<a href="${esc(it.issue_url)}">issue</a>`);
      if (it.opencode_pr_url) parts.push(`<a href="${esc(it.opencode_pr_url)}">PR</a>`);
      lines.push(`  └ ${esc(it.repository)}${parts.length ? " → " + parts.join(" | ") : ""}`);
    }
    await this.telegram.sendMessage(lines.join("\n"), "HTML");
  }

  async analyzeUiNeeds(repository: string): Promise<{ has_ui_work: boolean; improvements: string[] }> {
    const info = await this.getRepositoryInfo(repository);
    if (!info) return { has_ui_work: false, improvements: [] };
    const issues = await this.githubClient.getOpenIssues(repository, 30);
    const ui = issues.filter((i) => UI_KEYWORDS.some((k) => i.title.toLowerCase().includes(k) || (i.body ?? "").toLowerCase().includes(k)));
    const improvements = ui.slice(0, 5).map((i) => `Resolve UI issue: ${i.title}`);
    if (!(await this.githubClient.pathExists(repository, "DESIGN.md").catch(() => false))) improvements.push("Create DESIGN.md with design system documentation");
    return { has_ui_work: FRONTEND.includes(info.language) && improvements.length > 0, improvements };
  }

  async createUiImprovementIssue(repository: string, a: { improvements: string[] }): Promise<{ repository: string; issue_number: number; issue_url: string } | null> {
    const text = a.improvements.map((i) => `- ${i}`).join("\n");
    const fallback = `## Objective\nImprove the UI/UX per the points below.\n\n${text}`;
    let body = fallback;
    const ai = this.getAi();
    if (ai) {
      const prompt = `Repository: ${repository}\nUI/UX improvement opportunities found:\n${text}\n\nWrite a professional GitHub issue body that suggests these UI/UX improvements following modern web design best practices (vibrant colors, glassmorphism, responsive etc). Start with a '## Objective' section stating in 1-2 sentences exactly what should change and why, so it can be implemented without further clarification.`;
      try { body = (await ai.generate(prompt)).trim(); } catch (e: any) { this.log(`AI generation failed: ${e?.message ?? e}`, "WARNING"); }
    }
    body += "\n\n" + buildOriginMetadata(this.name, this.aiModel);
    try {
      const issue = await this.githubClient.createIssue(repository, { title: "UI/UX Improvement Suggestions", body, labels: [ROADMAP_LABEL] });
      await assignOwner(this.githubClient, issue, this.targetOwner, this.log);
      return { repository, issue_number: issue.number, issue_url: issue.html_url };
    } catch (e: any) { this.log(`Failed to create issue in ${repository}: ${e?.message ?? e}`, "WARNING"); return null; }
  }
}
