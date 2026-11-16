/** Git operations for Secret Remover: allowlist PR and history rewriting. */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { run, runChecked } from "../../utils/proc.ts";
import { authConfigArgs } from "../../utils/secure-git.ts";
import { assignOwner, buildPrBody, requestReviewOwner } from "../core/utils.ts";
import type { GithubClient } from "../../github/client.ts";

type Log = (m: string, level?: string) => void;
const git = (args: string[], cwd: string, timeoutMs?: number) => runChecked(["git", ...args], { cwd, timeoutMs });

export function buildSecurityBranch(repo: string, now = new Date()): string {
  const slug = repo.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/^-+|-+$/g, "");
  const ts = now.toISOString().replace(/[-:T]/g, "").slice(0, 14);
  return `agent/security-hardening-for-${slug}-${ts}`;
}

export async function getRemoteUrl(cloneDir: string): Promise<string> {
  try { const r = await run(["git", "remote", "get-url", "origin"], { cwd: cloneDir, timeoutMs: 10_000 }); return r.code === 0 ? r.stdout.trim() : ""; } catch { return ""; }
}

export function buildAllowlistToml(existing: string, findings: Record<string, any>[]): string {
  const blocks = findings.map((f) => ["[[allowlist]]", `description = ${JSON.stringify(`False positive: ${f.rule_id} in ${f.file}`)}`, `rules = [${JSON.stringify(f.rule_id)}]`, `paths = [${JSON.stringify(f.file)}]`].join("\n"));
  return (existing.trimEnd() + "\n\n" + blocks.join("\n\n")).trim() + "\n";
}

export async function applyAllowlistLocally(gh: GithubClient, repo: string, findings: Record<string, any>[], cloneDir: string, token: string, log: Log, defaultBranch = "main"): Promise<boolean> {
  const toml = join(cloneDir, ".gitleaks.toml");
  const content = buildAllowlistToml(existsSync(toml) ? readFileSync(toml, "utf8") : "", findings);
  const branch = buildSecurityBranch(repo), title = `Security hardening for ${repo}`;
  try {
    writeFileSync(toml, content);
    await git(["checkout", "-b", branch], cloneDir);
    await git(["config", "user.email", "secret-remover@github-assistance"], cloneDir);
    await git(["config", "user.name", "Secret Remover Agent"], cloneDir);
    await git(["add", ".gitleaks.toml"], cloneDir);
    await git(["commit", "-m", `chore: add gitleaks allowlist (${findings.length} entries)`], cloneDir);
    await git([...authConfigArgs(token), "push", "-u", "origin", branch], cloneDir);
    const body = buildPrBody("secret_remover", title, `Added ${findings.length} gitleaks allowlist entrie(s).`, "secret-remover");
    const pr = await gh.createPull(repo, { title: `[agent/secret_remover] ${title}`, body, head: branch, base: defaultBranch });
    await assignOwner(gh, pr, undefined, log); await requestReviewOwner(gh, pr, undefined, log);
    log(`Allowlist PR opened for ${repo}: ${pr.html_url}`);
    return true;
  } catch (e: any) { log(`Failed to apply allowlist for ${repo}: git command failed`, "WARNING"); return false; }
}

export async function removeSecretFromHistory(repo: string, finding: Record<string, any>, cloneDir: string, log: Log, token?: string): Promise<boolean> {
  const file = finding.file ?? "";
  if (!file) { log(`Cannot remove secret: missing file path for ${repo}`, "ERROR"); return false; }
  const remote = await getRemoteUrl(cloneDir);
  if (!remote) { log(`Cannot remove secret: no remote URL for ${repo}`, "ERROR"); return false; }
  try {
    const r = await run(["git-filter-repo", "--path", file, "--invert-paths", "--force"], { cwd: cloneDir, timeoutMs: 300_000 });
    if (r.timedOut) { log(`Timeout removing secret from ${repo}/${file}`, "ERROR"); return false; }
    if (r.code !== 0) { log(`git-filter-repo failed for ${repo}/${file}`, "ERROR"); return false; }
    // filter-repo strips the remote; the stored URL is token-free so re-adding cannot embed a credential.
    await git(["remote", "add", "origin", remote], cloneDir, 10_000);
    await git([...authConfigArgs(token), "push", "--force", "--all"], cloneDir, 120_000);
    await run(["git", ...authConfigArgs(token), "push", "--force", "--tags"], { cwd: cloneDir, timeoutMs: 120_000 });
    log(`Secret removed from history: ${repo}/${file}`);
    return true;
  } catch { log(`Error removing secret from ${repo}/${file}: git command failed`, "ERROR"); return false; }
}
