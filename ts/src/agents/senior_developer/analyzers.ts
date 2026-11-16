/** Repository analyzers for the Senior Developer agent (security, CI/CD, roadmap, debt, modernization, performance, AI). */
import type { BaseAgent } from "../base-agent.ts";
import type { AIClient } from "../../ai/client.ts";

type R = Record<string, any>;
const json = (s: string): R | null => { const m = /\{[\s\S]*\}/.exec(s); return m ? JSON.parse(m[0]) : null; };
const hasLabel = (i: any, names: string[]) => (i.labels ?? []).some((l: any) => names.includes((l.name ?? "").toLowerCase()));

export class SeniorDeveloperAnalyzer {
  constructor(private agent: BaseAgent, private ai: () => AIClient | null) {}
  private info(repo: string) { return this.agent.getRepositoryInfo(repo); }
  private async text(repo: string, path: string): Promise<string | null> { return (await this.agent.githubClient.getContents(repo, path))?.content ?? null; }

  async analyzeSecurity(repo: string): Promise<R> {
    if (!(await this.info(repo))) return { needs_attention: false };
    const issues: string[] = [];
    try {
      const c = await this.text(repo, ".gitignore");
      if (c === null) throw new Error("missing");
      if (!c.includes(".env")) issues.push("Missing .env in .gitignore");
      if (!c.toLowerCase().includes("secrets")) issues.push("Consider adding common secret patterns to .gitignore");
    } catch { issues.push("Missing .gitignore file"); }
    return { needs_attention: issues.length > 0, issues };
  }

  async analyzeCicd(repo: string): Promise<R> {
    if (!(await this.info(repo))) return { needs_improvement: false };
    const gh = this.agent.githubClient, improvements: string[] = [];
    try {
      const wf = await gh.listContents(repo, ".github/workflows");
      if (wf === null) improvements.push("Set up GitHub Actions for CI/CD");
      else if (!wf.length) improvements.push("No GitHub Actions workflows found");
    } catch { improvements.push("Set up GitHub Actions for CI/CD"); }
    try {
      const root = await gh.listContents(repo, "");
      if (root === null) improvements.push("Empty repository or no files found - add project structure and tests");
      else if (!root.some((i) => i.name.toLowerCase().includes("test"))) improvements.push("No test directory found - add comprehensive tests");
    } catch (e: any) {
      if (e?.status) improvements.push("Empty repository or no files found - add project structure and tests");
      else this.agent.log(`Unexpected error checking tests for ${repo}: ${e?.message ?? e}`, "WARNING");
    }
    return { needs_improvement: improvements.length > 0, improvements };
  }

  async analyzeRoadmapFeatures(repo: string): Promise<R> {
    if (!(await this.info(repo))) return { has_features: false };
    try {
      if (!(await this.agent.githubClient.pathExists(repo, "ROADMAP.md"))) return { has_features: false, features: [] };
      const feats = (await this.agent.githubClient.getOpenIssues(repo, 20)).filter((i) => hasLabel(i, ["feature", "enhancement"]));
      return { has_features: feats.length > 0, features: feats.slice(0, 5).map((i) => ({ title: i.title, number: i.number })) };
    } catch (e: any) {
      if (!e?.status) this.agent.log(`Unexpected error checking roadmap for ${repo}: ${e?.message ?? e}`, "WARNING");
      return { has_features: false, features: [] };
    }
  }

  async analyzeTechDebt(repo: string): Promise<R> {
    const info = await this.info(repo);
    if (!info) return { needs_attention: false };
    const items: string[] = [];
    try {
      if (!info.default_branch) return { needs_attention: false };
      const tree = await this.agent.githubClient.getTree(repo, info.default_branch);
      for (const i of tree) if (/\.(py|js|ts|go)$/.test(i.path) && i.size && i.size > 20480) items.push(`Large file detected: \`${i.path}\` (potential high complexity)`);
      const utils = tree.filter((i) => i.path.toLowerCase().includes("utils"));
      if (utils.length > 5) items.push(`High number of utility files (${utils.length})`);
    } catch (e: any) { if (!e?.status) this.agent.log(`Error in tech debt analysis for ${repo}: ${e?.message ?? e}`, "WARNING"); }
    return { needs_attention: items.length > 0, details: items.slice(0, 10).map((i) => `- ${i}`).join("\n") };
  }

  async analyzeModernization(repo: string): Promise<R> {
    const info = await this.info(repo);
    if (!info) return { needs_modernization: false };
    const needs: string[] = [];
    try {
      if (!info.default_branch) return { needs_modernization: false };
      const tree = await this.agent.githubClient.getTree(repo, info.default_branch);
      const hasTs = tree.some((i) => i.path.endsWith(".ts")), js = tree.filter((i) => i.path.endsWith(".js")).map((i) => i.path);
      if (js.length && hasTs) needs.push("Mixed JS/TS codebase - complete TypeScript migration");
      else if (js.length) needs.push("Legacy JavaScript codebase - consider TypeScript migration");
      if (js.length) {
        const c = (await this.text(repo, js[0])) ?? "";
        if (c.includes("require(") || c.includes("module.exports")) needs.push("CommonJS detected - migrate to ES Modules");
        if (c.includes(".then(")) needs.push("Legacy Promise chains detected - refactor to async/await");
      }
    } catch (e: any) { if (!e?.status) this.agent.log(`Error in modernization analysis for ${repo}: ${e?.message ?? e}`, "WARNING"); }
    return { needs_modernization: needs.length > 0, details: needs.map((n) => `- ${n}`).join("\n") };
  }

  async analyzePerformance(repo: string): Promise<R> {
    const info = await this.info(repo);
    if (!info) return { needs_optimization: false };
    const obs: string[] = [];
    try {
      try { if ((await this.text(repo, "package.json"))?.includes("lodash")) obs.push("Using heavy utility library (lodash)"); } catch (e: any) { if (!e?.status) throw e; }
      if (info.default_branch && (await this.agent.githubClient.getTree(repo, info.default_branch)).length > 200) obs.push("Large codebase - perform general performance audit");
    } catch (e: any) { if (!e?.status) this.agent.log(`Error in performance analysis for ${repo}: ${e?.message ?? e}`, "WARNING"); }
    return { needs_optimization: obs.length > 0, details: obs.map((o) => `- ${o}`).join("\n") };
  }

  async aiPoweredAudit(repo: string): Promise<R> {
    const ai = this.ai();
    if (!(await this.info(repo)) || !ai) return { needs_attention: false };
    const collected: string[] = [];
    for (const f of [".env.example", "Dockerfile", "pyproject.toml", "package.json", "README.md"]) {
      try { const c = await this.text(repo, f); if (c !== null) collected.push(`--- FILE: ${f} ---\n${c.slice(0, 2000)}`); } catch { continue; }
    }
    if (!collected.length) return { needs_attention: false };
    const prompt = `You are a Senior Security & Architecture auditor analyzing the repository '${repo}'.\nAnalyze these configuration files for security risks, misconfigurations, or missing best practices:\n\n${collected.join("\n\n")}\n\nRespond with a JSON object containing:\n{"needs_attention": bool, "findings": [str], "criticality": "low|medium|high"}`;
    try { const r = json(await ai.generate(prompt)); if (r) return r; } catch (e: any) { this.agent.log(`AI Audit failed for ${repo}: ${e?.message ?? e}`, "WARNING"); }
    return { needs_attention: false };
  }

  async aiPoweredFeatureEnhancement(repo: string): Promise<R> {
    const ai = this.ai();
    if (!(await this.info(repo)) || !ai) return { needs_enhancement: false };
    let readme = "No README.md found.", structure = "Could not retrieve structure.";
    try { readme = (await this.text(repo, "README.md")) ?? readme; } catch { /* keep default */ }
    try { const c = await this.agent.githubClient.listContents(repo, ""); if (c) structure = c.map((i) => `- ${i.name} (${i.type})`).join("\n"); } catch { /* keep default */ }
    const prompt = `You are a Lead Product Engineer analyzing '${repo}'.\nREADME:\n${readme.slice(0, 1500)}\n\nStructure:\n${structure}\n\nBased on the project description and structure, suggest ONE concrete and impactful feature improvement or a new high-value functionality.\nRespond with a JSON object containing:\n{"needs_enhancement": true, "suggestion": "Title of the enhancement", "details": "Detailed technical description of what to implement"}`;
    try { const r = json(await ai.generate(prompt)); if (r) return r; } catch (e: any) { this.agent.log(`Feature enhancement analysis failed for ${repo}: ${e?.message ?? e}`, "WARNING"); }
    return { needs_enhancement: false };
  }
}
