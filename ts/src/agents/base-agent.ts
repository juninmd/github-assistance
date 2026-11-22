/** Base class for all agents. */
import { RepositoryAllowlist } from "../config/allowlist.ts";
import type { GithubClient } from "../github/client.ts";
import { TelegramNotifier } from "../notifications/telegram.ts";
import { getLogger, type StructuredLogger } from "../utils/logger.ts";
import { RepositoryManager } from "./core/repo-manager.ts";
import * as utils from "./core/utils.ts";
import { runOpencodeTask } from "./opencode/local.ts";
import { OpencodeRunner } from "./opencode/runner.ts";
import type { AI } from "./registry.ts";
import { DEFAULT_PR_OPTIONS, type PrOptions } from "./core/pr-options.ts";

export type BaseDeps = {
  githubClient: GithubClient; allowlist: RepositoryAllowlist; telegram?: TelegramNotifier;
  targetOwner?: string; enforceRepositoryAllowlist?: boolean; ai?: AI; prOptions?: PrOptions;
};

export abstract class BaseAgent {
  abstract readonly persona: string;
  abstract readonly mission: string;
  githubClient: GithubClient; allowlist: RepositoryAllowlist; telegram: TelegramNotifier;
  targetOwner: string; enforceRepositoryAllowlist: boolean; prOptions: PrOptions;
  protected logger: StructuredLogger; protected repoMgr: RepositoryManager; protected opencode: OpencodeRunner;
  private instructionsCache: string | null = null;

  constructor(public name: string, d: BaseDeps) {
    this.githubClient = d.githubClient; this.allowlist = d.allowlist;
    this.telegram = d.telegram ?? new TelegramNotifier(); this.targetOwner = d.targetOwner ?? "juninmd";
    this.enforceRepositoryAllowlist = d.enforceRepositoryAllowlist ?? false;
    this.prOptions = d.prOptions ?? DEFAULT_PR_OPTIONS;
    this.logger = getLogger(name);
    this.repoMgr = new RepositoryManager(this.githubClient, this.allowlist, this.targetOwner, this.log);
    this.opencode = new OpencodeRunner(this.allowlist, this.log, this.githubClient, this.telegram, this.targetOwner);
  }
  abstract run(): Promise<Record<string, any>>;

  log = (message: string, level = "INFO"): void => { (this.logger as any)[level.toLowerCase() === "warn" ? "warning" : level.toLowerCase()]?.(message); };

  loadInstructions(): string { return (this.instructionsCache ||= utils.loadInstructions(this.name, this.log)); }
  loadTaskInstructions(template = "task-instructions.md", vars?: Record<string, unknown>) { return utils.loadTaskInstructions(this.name, template, vars, this.log); }
  getInstructionsSection(header: string) { return utils.getInstructionsSection(this.loadInstructions(), header); }
  getAllowedRepositories() { return this.repoMgr.getAllowedRepositories(this.enforceRepositoryAllowlist); }
  usesRepositoryAllowlist() { return this.enforceRepositoryAllowlist; }
  canWorkOnRepository(r: string) { return this.repoMgr.canWorkOn(r, this.enforceRepositoryAllowlist); }
  getRepositoryInfo(r: string) { return this.repoMgr.getInfo(r); }
  checkRateLimit() { return utils.checkGithubRateLimit(this.githubClient, this.log); }

  runOpencodeOnRepo(repository: string, instructions: string, title: string) { return this.opencode.runOnRepo(repository, instructions, title, this.name, this.prOptions); }
  async createOpencodeTask(repository: string, instructions: string, title: string, baseBranch?: string | null): Promise<Record<string, any>> {
    if (!this.canWorkOnRepository(repository)) throw new Error(`opencode denied: Repository ${repository} is not in allowlist`);
    let base = baseBranch;
    if (!base) { base = (await this.getRepositoryInfo(repository))?.default_branch; if (!base) throw new Error(`Could not determine default branch for ${repository}`); }
    return runOpencodeTask({ githubClient: this.githubClient, repository, instructions, title, baseBranch: String(base), log: this.log, agentName: this.name, prOptions: this.prOptions });
  }
  async openPullRequest(repository: string, branch: string, title: string, output: string, model = "opencode"): Promise<string> {
    const repo = await this.githubClient.getRepo(repository);
    const pr = await this.githubClient.createPull(repository, { title: `[agent/${this.name}] ${title}`, body: utils.buildPrBody(this.name, title, output, model), head: branch, base: repo.default_branch });
    await utils.assignOwner(this.githubClient, pr, this.targetOwner, this.log);
    await utils.requestReviewOwner(this.githubClient, pr, this.targetOwner, this.log);
    return pr.html_url;
  }
}
