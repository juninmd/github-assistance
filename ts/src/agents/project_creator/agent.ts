/** Project Creator - brainstorms ideas, creates repositories and delegates implementation to a Jules session. */
import { BaseAgent } from "../base-agent.ts";
import { makeAi, type AgentOpts } from "../agent-types.ts";
import type { AIClient } from "../../ai/client.ts";
import { assignOwner, ensureLabel, ROADMAP_ACTIVE_LABEL, ROADMAP_LABEL } from "../core/utils.ts";
import { GithubError } from "../../github/client.ts";
import { TelegramNotifier } from "../../notifications/telegram.ts";
import { IdeationPipeline } from "./ideation/pipeline.ts";
import { buildPortfolio } from "./ideation/portfolio.ts";
import { MarketResearcher } from "./ideation/research.ts";
import type { Rng } from "./ideation/seed.ts";

type R = Record<string, any>;
const SKILLS_DIRECTIVE = "**Agent rules (mandatory):** whoever executes this issue (opencode, Jules or any agent) must follow the skills in https://github.com/juninmd/skills and the global instructions in https://github.com/juninmd/skills/blob/master/.agents/AGENTS.md, and read them before changing code.";
export const MAX_ROADMAP_ISSUES = 12;
const AUTONOMOUS_NOTICE = "| 🤖 Criado de forma autônoma pelo agente github-assistance. Autonomously created by the github-assistance AI agent.";
const esc = TelegramNotifier.escapeHtml;

export class ProjectCreatorAgent extends BaseAgent {
  aiClient: AIClient | null; private rng?: Rng;
  constructor(o: AgentOpts) {
    super("project_creator", { ...o, enforceRepositoryAllowlist: true });
    this.aiClient = o.aiClient !== undefined ? o.aiClient : makeAi({ provider: o.ai?.provider ?? "litellm", model: o.ai?.model ?? "cloud/auto", config: o.ai?.config }).client;
    this.rng = o.rng;
  }
  get persona() { return this.getInstructionsSection("## Persona"); }
  get mission() { return this.getInstructionsSection("## Mission"); }

  async run(): Promise<R> {
    this.log("Starting Project Creator workflow");
    try {
      const idea = await this.generateProjectIdea();
      if (!idea) return { status: "failed", reason: "could_not_generate_idea" };
      let repoName: string | undefined = idea.repository_name;
      const title = idea.title || repoName, projectIdea = idea.idea_description, tech = idea.tech_stack ?? "", julesPrompt = idea.jules_prompt ?? "";
      if (!repoName || !projectIdea || !julesPrompt) return { status: "failed", reason: "invalid_idea_format" };
      repoName = repoName.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-").replace(/^-+|-+$/g, "");
      const full = `${this.targetOwner}/${repoName}`;
      await this.notifyIdea(repoName, projectIdea, tech);
      const instructions = this.loadJulesInstructions("jules-instructions.md", { repository_name: full, project_title: title, project_idea: projectIdea, tech_stack: tech, jules_prompt: julesPrompt });
      const tagline = String(idea.tagline ?? "").trim();
      const repo = await this.createGithubRepo(repoName, tagline || projectIdea);
      if (!repo) return { status: "failed", reason: "repo_creation_failed" };
      if (!(await this.ensureMasterBranch(repo))) return { status: "failed", reason: "master_branch_failed" };
      this.allowlist.addRepository(full);
      if (!(await this.isJulesSourceAvailable(full))) { await this.notifyFailed(`Repository ${full} is not connected as a Jules source`); return { status: "failed", reason: "jules_source_missing", repository: full }; }
      const session = await this.createJulesSession(full, instructions, `Initial implementation for ${title}`, { baseBranch: "master" });
      const roadmapIssues = await this.createRoadmapBacklog(repo, idea.roadmap_features ?? []);
      const url = `https://github.com/${full}`;
      await this.notifyCreated(full, projectIdea, null, url);
      return { status: "session_created", repository: full, idea: projectIdea, session_id: session.id, repo_url: url, roadmap_issues: roadmapIssues };
    } catch (e: any) { this.log(`Project Creator failed: ${e?.message ?? e}`, "ERROR"); await this.notifyFailed(String(e?.message ?? e)); return { status: "failed" }; }
  }

  private async isJulesSourceAvailable(repository: string): Promise<boolean> {
    const name = this.julesClient.getSourceName(repository);
    try { return (await this.julesClient.listSources()).some((s: R) => s.name === name); }
    catch (e: any) { this.log(`Failed to list Jules sources: ${e?.message ?? e}`, "ERROR"); return false; }
  }

  private async safeSend(text: string, label: string, replyMarkup?: object) {
    try { await this.telegram.sendMessage(text, "HTML", replyMarkup); } catch (e: any) { this.log(`Failed to send ${label} notification: ${e?.message ?? e}`, "WARNING"); }
  }
  private notifyIdea(repo: string, idea: string, tech = "") {
    const lines = ["💡 <b>NOVA IDEIA DE PROJETO</b>", "──────────────────────", `📦 <b>Repositório:</b> <code>${esc(repo)}</code>`];
    if (tech) lines.push(`🛠 <b>Stack:</b> <code>${esc(tech)}</code>`);
    lines.push("📝 <b>Descrição:</b>", `<i>${esc(idea)}</i>`, "──────────────────────", "⚙️ Abrindo sessão no Jules…");
    return this.safeSend(lines.join("\n"), "idea");
  }
  private notifyCreated(full: string, idea: string, sessionId?: string | null, repoUrl?: string | null) {
    const url = repoUrl || `https://github.com/${full}`;
    let text = `✅ <b>PROJETO CRIADO COM SUCESSO</b>\n──────────────────────\n📦 <b>Repositório:</b> <code>${esc(full)}</code>\n📝 <b>Ideia:</b> <i>${esc(idea.slice(0, 250))}</i>\n`;
    if (sessionId) text += `⚙️ <b>Jules Sessão:</b> <code>${esc(sessionId)}</code>\n`;
    text += `──────────────────────\n🔗 <a href="${url}">Abrir no GitHub</a>`;
    return this.safeSend(text, "created", { inline_keyboard: [[{ text: "🔗 Ver repositório", url }]] });
  }
  private notifyFailed(error = "Unknown error") { return this.safeSend(`❌ <b>PROJECT CREATOR — FALHA</b>\n──────────────────────\n<pre>${esc(error.slice(0, 300))}</pre>`, "failure"); }

  /** Create a private GitHub repository for autonomous implementation. */
  async createGithubRepo(name: string, summary: string): Promise<R | null> {
    const description = `${summary.slice(0, 250)} ${AUTONOMOUS_NOTICE}`.slice(0, 350);
    try { const repo = await this.githubClient.createUserRepo({ name, description, private: true, autoInit: true }); this.log(`Created repository: ${this.targetOwner}/${name}`); return repo; }
    catch (e: any) {
      this.log(e instanceof GithubError ? `Failed to create repository: ${e.status} ${JSON.stringify(e.data)}` : `Unexpected error creating repository: ${e?.message ?? e}`, "ERROR");
      return null;
    }
  }

  /** Jules starts from master regardless of the account default branch. */
  async ensureMasterBranch(repo: R): Promise<boolean> {
    const full = repo.full_name ?? `${this.targetOwner}/${repo.name}`;
    try {
      const def = repo.default_branch ?? "master";
      if (def !== "master") {
        const ref = await this.githubClient.getRef(full, `heads/${def}`);
        await this.githubClient.createRef(full, "refs/heads/master", ref.object.sha);
        await this.githubClient.editRepo(full, { default_branch: "master" });
      }
      return true;
    } catch (e: any) {
      if (e instanceof GithubError) {
        if (e.status === 422) {
          try { await this.githubClient.editRepo(full, { default_branch: "master" }); return true; }
          catch (ee: any) { this.log(`Failed to set master as default branch: ${ee?.message ?? ee}`, "ERROR"); return false; }
        }
        this.log(`Failed to ensure master branch: ${e.status} ${JSON.stringify(e.data)}`, "ERROR"); return false;
      }
      this.log(`Unexpected error ensuring master branch: ${e?.message ?? e}`, "ERROR"); return false;
    }
  }

  /** One 'roadmap' + 'jules' issue per post-MVP feature; labeling 'jules' natively triggers a Jules session. */
  async createRoadmapBacklog(repo: R, features: unknown[]): Promise<string[]> {
    if (!features.length) return [];
    const full = repo.full_name ?? `${this.targetOwner}/${repo.name}`;
    await ensureLabel(this.githubClient, full, ROADMAP_LABEL, "0e8a16", "Backlog item for autonomous evolution", this.log);
    await ensureLabel(this.githubClient, full, ROADMAP_ACTIVE_LABEL, "6f42c1", "Triggers a Jules session", this.log);
    const urls: string[] = [];
    for (const f of features.slice(0, MAX_ROADMAP_ISSUES)) {
      const [title, objective] = ProjectCreatorAgent.splitFeature(f);
      try {
        const issue = await this.githubClient.createIssue(full, {
          title: title.slice(0, 250), labels: [ROADMAP_LABEL, ROADMAP_ACTIVE_LABEL],
          body: `## Objective\n${objective}\n\n${SKILLS_DIRECTIVE}\n\n${AUTONOMOUS_NOTICE}\n\nPart of the initial roadmap for this project. When implementing, keep the change scoped to this item, open a PR, and include \`Closes #<this issue's number>\` in the PR description so this issue closes automatically on merge.`,
        });
        await assignOwner(this.githubClient, issue, this.targetOwner, this.log);
        urls.push(issue.html_url);
      } catch (e: any) { this.log(`Failed to create roadmap issue for '${title}': ${e?.message ?? e}`, "WARNING"); }
    }
    return urls;
  }

  /** Accepts `{title, objective}` (preferred) or a plain string. */
  static splitFeature(f: unknown): [string, string] {
    if (f && typeof f === "object") { const o = f as R, title = String(o.title || "Roadmap item").trim(); return [title, String(o.objective || title).trim()]; }
    const t = String(f).trim(); return [t, t];
  }

  private async fetchExistingRepos(): Promise<R[]> {
    try { return await this.githubClient.getUserRepos({ sort: "updated", limit: null }); }
    catch (e: any) { this.log(`Failed to fetch existing repos: ${e?.message ?? e}`, "WARNING"); return []; }
  }

  /** Multi-stage ideation (seed, diverge, critique, specify, gate). */
  async generateProjectIdea(): Promise<R | null> {
    const ai = this.aiClient;
    if (!ai) { this.log("AI client is not configured.", "ERROR"); return null; }
    const repos = await this.fetchExistingRepos();
    const names = repos.map((r) => r.name), history = repos.map((r) => `${r.name} ${(r.description ?? "").slice(0, 90)}`.trim());
    const pipeline = new IdeationPipeline((p) => ai.generate(p), this.log, { researcher: new MarketResearcher(this.githubClient, this.log), owner: this.targetOwner, rng: this.rng });
    const idea = await pipeline.run(history, names, buildPortfolio(repos, this.targetOwner));
    if (!idea) this.log("Ideation pipeline produced no idea that passed the quality gate", "WARNING");
    return idea;
  }
}
