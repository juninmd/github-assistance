/** Classifies and remediates findings for a single repository. */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { AIClient } from "../../ai/client.ts";
import type { GithubClient } from "../../github/client.ts";
import type { TelegramNotifier } from "../../notifications/telegram.ts";
import { runChecked } from "../../utils/proc.ts";
import { authConfigArgs, githubCloneUrl } from "../../utils/secure-git.ts";
import * as gitUtils from "./git-utils.ts";
import * as utils from "./utils.ts";
import { sendFindingNotification } from "./telegram-summary.ts";

type Log = (m: string, level?: string) => void;

export class FindingProcessor {
  constructor(private ai: AIClient, private telegram: TelegramNotifier, private gh: GithubClient, private log: Log) {}

  /** Falls back to IGNORE on any AI error to avoid destructive mistakes. */
  async analyze(finding: Record<string, any>): Promise<{ action: string; reason: string }> {
    return this.ai.classifySecretFinding(finding, String(finding.redacted_context ?? ""));
  }

  async processRepo(repo: string, findings: Record<string, any>[], defaultBranch: string) {
    this.log(`Analysing ${findings.length} finding(s) for ${repo}`);
    let ignored = 0, removed = 0;
    const actions: Record<string, any>[] = [], ignoredFindings: Record<string, any>[] = [];
    const token = process.env.GITHUB_TOKEN;
    if (!token) throw new Error("GITHUB_TOKEN not available for repository analysis");
    const tmp = mkdtempSync(join(tmpdir(), "secret-remover-"));
    try {
      const cloneDir = join(tmp, "repo");
      this.log(`Cloning ${repo} for analysis...`);
      await runChecked(["git", ...authConfigArgs(token), "clone", "--single-branch", "--branch", defaultBranch, githubCloneUrl(repo), cloneDir]);
      for (const finding of findings) {
        const f: Record<string, any> = { ...finding };
        f.redacted_context = utils.buildRedactedContext(cloneDir, f);
        const originalLine = utils.getOriginalLine(cloneDir, f);
        const decision = await this.analyze(f);
        f._action = decision.action; f._reason = decision.reason ?? "";
        const sha = f.commit ?? "HEAD", file = f.file ?? "", line = parseInt(f.line, 10) || 0;
        if (decision.action === "REMOVE_FROM_HISTORY") {
          const ok = await gitUtils.removeSecretFromHistory(repo, f, cloneDir, this.log, token);
          actions.push({ finding: f, status: ok ? "REMOVED" : "ERROR" });
          if (ok) removed++;
        } else { ignored++; ignoredFindings.push(f); actions.push({ finding: f, status: "IGNORED" }); }
        await sendFindingNotification(this.telegram, { repo, finding: f, action: decision.action, originalLine,
          commitUrl: utils.buildCommitUrl(repo, sha), fileLineUrl: utils.buildFileLineUrl(repo, sha, file, line), repoUrl: utils.buildRepoUrl(repo) });
      }
      if (ignoredFindings.length) {
        const ok = await gitUtils.applyAllowlistLocally(this.gh, repo, ignoredFindings, cloneDir, token, this.log, defaultBranch);
        actions.push({ status: ok ? "ALLOWLIST_APPLIED" : "ALLOWLIST_ERROR", findings_count: ignoredFindings.length });
      }
    } finally { rmSync(tmp, { recursive: true, force: true }); }
    return { repository: repo, ignored, to_remove: removed, actions };
  }
}
