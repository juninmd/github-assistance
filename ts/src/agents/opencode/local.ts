/** Run opencode locally against a repository: clone, implement, push, open a PR. */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { semanticMessage } from "../core/commit-message.ts";
import { assignOwner, buildPrBody, requestReviewOwner } from "../core/utils.ts";
import { selectFreeOpencodeModel } from "./models.ts";
import * as tokenix from "../../utils/tokenix.ts";
import { run, type RunResult } from "../../utils/proc.ts";
import { scanClone } from "../../utils/secret-scan.ts";
import { authConfigArgs, githubCloneUrl, redactSecrets, scrubEnv } from "../../utils/secure-git.ts";
import type { GithubClient } from "../../github/client.ts";

const OPENCODE_TIMEOUT_MS = 1_200_000, GIT_TIMEOUT_MS = 300_000;
type Log = (m: string, level?: string) => void;
const redact = (t?: string | null) => redactSecrets(t).trim();
const opencodeCmd = () => Bun.which("opencode") ?? "opencode";
export const slugify = (title: string) => title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48) || "task";

class GitError extends Error { constructor(public stderr: string, m: string) { super(m); } }
async function git(args: string[], cwd: string): Promise<RunResult> {
  const r = await run(args, { cwd, timeoutMs: GIT_TIMEOUT_MS });
  if (r.timedOut) throw Object.assign(new Error("timeout"), { timedOut: true });
  if (r.code !== 0) throw new GitError(redact(r.stderr), `git failed: ${redact(r.stderr).slice(0, 200)}`);
  return r;
}
const result = (status: string, repository: string, extra: Record<string, any> = {}) => ({ status, task_url: null, task_id: null, engine: "opencode-local", repository, ...extra });

/** `task_created` when a PR is opened; otherwise `no_changes` or a failure reason. */
export async function runOpencodeTask(o: { githubClient: GithubClient; repository: string; instructions: string; title: string; baseBranch: string; log: Log; agentName?: string }): Promise<Record<string, any>> {
  const { githubClient, repository, instructions, title, baseBranch, log } = o, agentName = o.agentName ?? "github-assistance";
  const token = process.env.GITHUB_TOKEN || process.env.GH_PAT || "";
  if (!token) return result("failed", repository, { error: "missing GITHUB_TOKEN" });
  const branch = `opencode/${slugify(title)}`;
  const tmp = mkdtempSync(join(tmpdir(), "oc-"));
  let usedModel = "";
  try {
    const dir = join(tmp, "repo");
    await git(["git", ...authConfigArgs(token), "clone", "--depth=1", githubCloneUrl(repository), dir], tmp);
    await git(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], dir);
    await git(["git", "config", "user.name", "github-actions[bot]"], dir);
    await git(["git", "checkout", "-b", branch], dir);
    const outcome = await tokenix.session(dir, async () => {
      const env = scrubEnv();
      env.NODE_OPTIONS ??= "--max-old-space-size=2048"; env.NODE_ENV ??= "production";
      const maxAttempts = parseInt(process.env.OPENCODE_RUN_MAX_ATTEMPTS ?? "2", 10) || 2;
      let oc: RunResult | null = null;
      usedModel = await selectFreeOpencodeModel(0);
      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        usedModel = await selectFreeOpencodeModel(attempt);
        log(`Running opencode (${attempt + 1}/${maxAttempts}; model: ${usedModel})`, "INFO");
        oc = await run([opencodeCmd(), "run", "--model", usedModel, instructions], { cwd: dir, env, timeoutMs: OPENCODE_TIMEOUT_MS });
        if (oc.timedOut) throw Object.assign(new Error("timeout"), { timedOut: true });
        if (oc.code === 0) break;
        log(`opencode failed with ${usedModel}: ${redact(oc.stderr).slice(0, 200)}`, "WARNING");
      }
      if (!oc || oc.code !== 0) { log(`opencode failed for ${repository}: ${redact(oc?.stderr ?? "unknown").slice(0, 300)}`, "WARNING"); return result("opencode_failed", repository, { error: "opencode run failed" }); }
      const st = await run(["git", "status", "--porcelain"], { cwd: dir, timeoutMs: 60_000 });
      if (!st.stdout.trim()) { log(`opencode made no changes for ${repository}`, "INFO"); return result("no_changes", repository); }
      await git(["git", "add", "-A"], dir);
      const findings = await scanClone(dir);
      if (findings.length) {
        const detail = findings.slice(0, 8).map((h) => `${h.file}:${h.line} -> ${h.rule_id}`).join("; ");
        log(`Push blocked for ${repository}: secret found: ${detail}`, "ERROR");
        return result("push_blocked_secret", repository, { findings: detail });
      }
      await git(["git", "commit", "-m", semanticMessage("chore", "opencode", title)], dir);
      await git(["git", ...authConfigArgs(token), "push", "origin", branch], dir);
      return null;
    });
    if (outcome) return outcome;
  } catch (e: any) {
    if (e?.timedOut) return result("failed", repository, { error: "opencode/git timed out" });
    if (e instanceof GitError) return result("failed", repository, { error: `git failed: ${redact(e.stderr).slice(0, 200)}` });
    log(`opencode local run errored for ${repository}: ${e?.name}`, "WARNING");
    return result("failed", repository, { error: e?.name ?? "Error" });
  } finally { rmSync(tmp, { recursive: true, force: true }); }

  try {
    const pr = await githubClient.createPull(repository, { title, body: buildPrBody(agentName, title, instructions, usedModel), head: branch, base: baseBranch });
    await assignOwner(githubClient, pr, undefined, log);
    await requestReviewOwner(githubClient, pr, undefined, log);
    log(`Opened PR #${pr.number} for ${repository} via opencode`, "INFO");
    return result("task_created", repository, { task_url: pr.html_url, task_id: pr.number });
  } catch (e: any) {
    log(`Failed to open PR for ${repository}: ${e?.name}`, "WARNING");
    return result("failed", repository, { error: `pr creation failed: ${e?.name}` });
  }
}
