/** Code Reviewer Agent - automated AI code review of open PRs. */
import { BaseAgent } from "../base-agent.ts";
import { makeAi, type AgentOpts } from "../agent-types.ts";
import { AgentMetrics } from "../core/metrics.ts";
import { buildOriginMetadata } from "../core/utils.ts";
import { extractJsonObject, type AIClient } from "../../ai/client.ts";
import { redactSecrets } from "../../utils/secure-git.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";

export class CodeReviewerAgent extends BaseAgent {
  private aiLabel: string; private _ai: AIClient | null = null; private aiOpts: AgentOpts["ai"];
  constructor(o: AgentOpts) { super("code_reviewer", o); this.aiOpts = o.ai; this.aiLabel = makeAi(o.ai).label; if (o.aiClient) this._ai = o.aiClient; }
  get persona() { return "Code Reviewer Agent — Expert in code quality, best practices, and bug detection."; }
  get mission() { return "Review pull requests for code quality, maintainability, best practices, potential bugs, security issues, and performance considerations."; }
  private get ai(): AIClient { return (this._ai ||= makeAi(this.aiOpts).client); }

  async run() {
    const metrics = new AgentMetrics(this.name), reviews: any[] = [], failed: any[] = [];
    try {
      this.log("Starting code review agent...");
      const repos = await this.getAllowedRepositories();
      this.log(`Reviewing PRs in ${repos.length} repositories`);
      for (const repo of repos) {
        try {
          const prs = await this.githubClient.getPulls(repo);
          this.log(`Found ${prs.length} open PRs in ${repo}`);
          for (const pr of prs) {
            try {
              if (await this.hasRecentReview(pr)) continue;
              const r = await this.reviewPullRequest(pr);
              if (r.success) { reviews.push(r); metrics.incrementProcessed(); } else { failed.push(r); metrics.incrementFailed(); }
            } catch (e: any) { this.log(`Error reviewing PR ${pr.number}: ${e?.message ?? e}`, "ERROR"); metrics.addError(`PR review failed: ${e?.message ?? e}`); failed.push({ pr: pr.number, error: String(e?.message ?? e) }); metrics.incrementFailed(); }
          }
        } catch (e: any) { this.log(`Error processing repository ${repo}: ${e?.message ?? e}`, "ERROR"); metrics.addError(`Repository processing failed: ${e?.message ?? e}`); }
      }
      await this.sendSummary(reviews, failed);
    } catch (e: any) { this.log(`Code review agent failed: ${e?.message ?? e}`, "ERROR"); metrics.addError(`Agent execution failed: ${e?.message ?? e}`); }
    return { reviews_performed: reviews, failed, metrics: metrics.finalize() };
  }

  private async hasRecentReview(pr: any): Promise<boolean> {
    let bot = "";
    try { bot = await this.githubClient.getAuthenticatedLogin(); } catch { /* unknown */ }
    for (const c of await this.githubClient.getIssueComments(pr.base.repo.full_name, pr.number)) {
      const body = c.body ?? "";
      const isReview = body.includes("## AI Code Review") || body.includes("<!-- code-review -->") || body.includes("<!-- opencode-review -->");
      if (isReview && (!bot || c.user?.login === bot)) return true;
    }
    return false;
  }

  private async reviewPullRequest(pr: any) {
    const n = pr.number, files = await this.githubClient.getFiles(pr.base.repo.full_name, n);
    const changes = files.map((f: any) => `File: ${f.filename} (${f.status}, +${f.additions}/-${f.deletions})\n\`\`\`diff\n${(f.patch ?? "").slice(0, 3000)}\n\`\`\``);
    if (!changes.length) { this.log(`PR #${n}: no file changes to review`); return { success: true, pr_number: n, issues_found: [], suggestions: [] }; }
    const prompt = "You are a senior code reviewer. Analyze this pull request and provide feedback.\n" + `PR #${n}: ${pr.title}\n\n` + "Changes:\n" + changes.slice(0, 5).join("\n---\n") + "\n\n" +
      "Respond with ONLY valid JSON:\n" + '{"issues": [{"severity": "high|medium|low", "file": "filename", "line": null, "description": "issue description", "suggestion": "how to fix"}], "summary": "overall assessment", "score": 0-10}';
    let issues: any[] = [], summary = "Review completed.";
    try {
      const data = extractJsonObject(await this.ai.generate(prompt));
      if (data) { issues = Array.isArray(data.issues) ? data.issues : []; summary = data.summary ?? summary; }
    } catch (e: any) {
      this.log(`AI review failed for PR #${n}: ${e?.message ?? e}`, "WARNING");
      return { success: true, pr_number: n, issues_found: [], suggestions: [], error: String(e?.message ?? e) };
    }
    await this.postReview(pr, issues, summary, n);
    return { success: true, pr_number: n, issues_found: issues, suggestions: issues };
  }

  private async postReview(pr: any, issues: any[], summary: string, n: number) {
    const parts = ["<!-- code-review -->\n", "## AI Code Review\n", `**Summary:** ${summary}\n`];
    if (issues.length) {
      parts.push("\n### Issues Found\n");
      for (const i of issues.slice(0, 10)) {
        parts.push(`- **[${String(i.severity ?? "info").toUpperCase()}]** ${i.file ?? ""}: ${i.description ?? ""}`);
        if (i.suggestion) parts.push(`  > ${i.suggestion}`);
      }
    } else parts.push("\nNo issues found. The code looks good! 🎉");
    parts.push("\n" + buildOriginMetadata("code_reviewer", this.aiLabel));
    const full = parts.join("\n");
    try {
      let posted = false;
      const inline = issues.slice(0, 10).filter((i) => i.file && Number.isInteger(i.line) && i.line > 0 && i.description).map((i) => {
        let text = `**[${String(i.severity ?? "info").toUpperCase()}]** ${i.description}`;
        if (i.suggestion) text += `\n\n> ${i.suggestion}`;
        return { path: i.file, line: i.line, body: redactSecrets(text) };
      });
      if (inline.length) { try { await this.githubClient.createReview(pr, { body: redactSecrets(full), event: "COMMENT", comments: inline }); posted = true; } catch { posted = false; } }
      if (!posted) await this.githubClient.commentOnPr(pr, redactSecrets(full));
      await this.telegram.sendMessage(`👀 <b>CODE REVIEW</b> PR #${n} em <code>${TelegramNotifier.escapeHtml(pr.base.repo.full_name)}</code> — ${issues.length} issues encontradas`, "HTML");
    } catch (e: any) { this.log(`Failed to post review for PR #${n}: ${e?.message ?? e}`, "WARNING"); }
  }

  private async sendSummary(reviews: any[], failures: any[]) {
    if (!reviews.length && !failures.length) return;
    await this.telegram.sendMessage(["👀 <b>CODE REVIEWER — RESUMO</b>", "──────────────────────", `✅ <b>Reviews realizados:</b> <code>${reviews.length}</code>`, `❌ <b>Falhas:</b> <code>${failures.length}</code>`].join("\n"), "HTML");
  }
}
