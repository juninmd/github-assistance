/** Repository analysis and roadmap instruction generation for the Product Manager. */
import type { AIClient } from "../../ai/client.ts";
import type { BaseAgent } from "../base-agent.ts";

export class RoadmapGenerator {
  constructor(private agent: BaseAgent, private ai: () => AIClient | null) {}

  /** True when ROADMAP.md was committed within the last 7 days. */
  async isRoadmapUpToDate(repo: any): Promise<boolean> {
    try {
      const [latest] = await this.agent.githubClient.getPathCommits(repo.full_name, "ROADMAP.md", 1);
      if (!latest) return false;
      return Date.now() - Date.parse(latest.commit.author.date) < 7 * 86400_000;
    } catch (e: any) {
      if (e?.status === undefined) this.agent.log(`Error checking ROADMAP.md freshness: ${e?.message ?? e}`, "WARNING");
      return false;
    }
  }

  async analyzeRepository(repo: any) {
    const issues = await this.agent.githubClient.getOpenIssues(repo.full_name, 50);
    const has = (i: any, names: string[]) => (i.labels ?? []).some((l: any) => names.includes((l.name ?? "").toLowerCase()));
    const bugs = issues.filter((i) => has(i, ["bug", "defect"])), features = issues.filter((i) => has(i, ["feature", "enhancement"])), debt = issues.filter((i) => has(i, ["tech-debt", "refactor"]));
    const ai = await this.analyzeIssuesWithAi(issues, repo.description ?? "");
    return {
      summary: ai.ai_summary || `Repository has ${issues.length} open issues`,
      priorities: ai.priorities || [{ category: "Bugs", count: bugs.length, urgency: "high" }, { category: "Features", count: features.length, urgency: "medium" }, { category: "Technical Debt", count: debt.length, urgency: "low" }],
      total_issues: issues.length, repository_description: repo.description || "No description", primary_language: repo.language || "Unknown",
    } as Record<string, any>;
  }

  private async analyzeIssuesWithAi(issues: any[], description: string): Promise<Record<string, any>> {
    const ai = this.ai();
    if (!ai || !issues.length) return {};
    const text = issues.map((i) => `- [${i.number}] ${i.title}: ${(i.labels ?? []).map((l: any) => l.name).join(", ")}`).join("\n");
    const prompt = `You are a Product Manager analyzing a repository.\nRepository Description: ${description}\nHere are the current open issues:\n${text}\n\n` +
      'Analyze these issues and provide a brief strategic summary and a list of priorities. Respond EXACTLY with the following JSON format and nothing else:\n{\n  "ai_summary": "A brief 2-sentence summary.",\n  "priorities": [{"category": "Category Name", "count": 1, "urgency": "high"}]\n}';
    try { const m = /\{[\s\S]*\}/.exec(await ai.generate(prompt)); if (m) return JSON.parse(m[0]); }
    catch (e: any) { this.agent.log(`AI analysis failed: ${e?.message ?? e}`, "WARNING"); }
    return {};
  }

  generateInstructions(repository: string, a: Record<string, any>): string {
    const priorities = (a.priorities ?? []).map((p: any) => `- ${p.category}: ${p.count} items (urgency: ${p.urgency})`).join("\n");
    return this.agent.loadJulesInstructions("jules-instructions.md", { repository, repository_description: a.repository_description ?? "No description", primary_language: a.primary_language ?? "Unknown", total_issues: a.total_issues ?? 0, priorities });
  }
}
