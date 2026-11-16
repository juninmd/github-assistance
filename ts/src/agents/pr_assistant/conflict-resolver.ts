/** Autonomous merge conflict resolution for PR Assistant (clone → merge base → resolve per file → validate → push). */
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { getAiClient, type AIClient } from "../../ai/client.ts";
import { DEFAULT_OLLAMA_MODEL } from "../../config/settings.ts";
import type { PR } from "../../github/client.ts";
import { run } from "../../utils/proc.ts";
import { authConfigArgs, githubCloneUrl, scrubEnv } from "../../utils/secure-git.ts";
import { semanticMessage } from "../core/commit-message.ts";
import { DEFAULT_OPENCODE_MODEL } from "../core/utils.ts";
import { PREFERRED_FREE_MODEL } from "../opencode/models.ts";
import { runProjectChecks } from "./build-check.ts";
import { hunkThreshold, resolveByHunks } from "./conflict-hunks.ts";
import { getConflictedFiles, GitCommandError, pythonBin, redact, runGit, safeCmd } from "./git.ts";

const OPENCODE_RESOLUTION_TIMEOUT = 600, DEFAULT_MAX_CONFLICTED_FILES = 20, MARKER = "<<<<<<< HEAD";
const envInt = (n: string, d: number) => { const v = parseInt(process.env[n] || "", 10); return Number.isNaN(v) ? d : v; };
const truthy = (n: string) => ["1", "true", "yes", "on"].includes((process.env[n] ?? "").toLowerCase());
export const opencodeTimeout = () => envInt("CONFLICT_OPENCODE_TIMEOUT", OPENCODE_RESOLUTION_TIMEOUT);
export const maxConflictedFiles = () => envInt("CONFLICT_MAX_FILES", DEFAULT_MAX_CONFLICTED_FILES);
/** opencode-based conflict resolution is opt-in (CONFLICT_OPENCODE_ENABLED). */
export const opencodeConflictEnabled = () => truthy("CONFLICT_OPENCODE_ENABLED");
export const opencodeCmd = () => Bun.which("opencode") ?? "opencode";

export async function setupCloneEnvironment(tmp: string, headClone: string): Promise<string> {
  const dir = join(tmp, "repo");
  await runGit(["git", ...authConfigArgs(), "clone", "--depth=100", "--no-single-branch", headClone, dir], tmp);
  await runGit(["git", "config", "user.email", process.env.GIT_AUTHOR_EMAIL ?? "gh-assistance[bot]@users.noreply.github.com"], dir);
  await runGit(["git", "config", "user.name", process.env.GIT_AUTHOR_NAME ?? "gh-assistance[bot]"], dir);
  return dir;
}

/** Attempt the merge, retrying with a full clone if the shallow depth is insufficient. `[rc, stderr, conflicted]`; rc -1 = unrelated histories. */
export async function tryMergeBase(dir: string, baseClone: string, headBranch: string, baseBranch: string): Promise<[number, string, string[]]> {
  await runGit(["git", "checkout", headBranch], dir);
  await runGit(["git", "remote", "add", "upstream", baseClone], dir);
  await runGit(["git", ...authConfigArgs(), "fetch", "--depth=100", "upstream", baseBranch], dir);
  let m = await run(["git", "merge", `upstream/${baseBranch}`], { cwd: dir, timeoutMs: 120_000 });
  let stderr = m.stderr.trim();
  if (m.code === 0) return [0, stderr, []];
  if (stderr.includes("fatal: refusing to merge unrelated histories") || stderr.includes("fatal: no merge base")) {
    await runGit(["git", ...authConfigArgs(), "fetch", "--unshallow"], dir);
    m = await run(["git", "merge", `upstream/${baseBranch}`], { cwd: dir, timeoutMs: 300_000 });
    stderr = m.stderr.trim();
    if (m.code !== 0 && (stderr.includes("fatal: refusing to merge unrelated histories") || stderr.includes("fatal: no merge base"))) return [-1, stderr, []];
  }
  return [m.code, stderr, await getConflictedFiles(dir)];
}

/** Delete/add conflicts are detected but never resolved automatically. */
export async function handleDeleteAddConflict(dir: string, file: string): Promise<[boolean, string]> {
  if ((await run(["git", "rev-parse", "MERGE_HEAD"], { cwd: dir })).code !== 0) return [false, ""];
  const inHead = (await run(["git", "cat-file", "-e", `HEAD:${file}`], { cwd: dir })).code === 0;
  const inMerge = (await run(["git", "cat-file", "-e", `MERGE_HEAD:${file}`], { cwd: dir })).code === 0;
  return inHead !== inMerge ? [false, "manual-delete-add"] : [false, ""];
}

// Lockfiles are never merged by hand: the conflicted copy is replaced by the head version and regenerated from the merged manifest.
export const LOCKFILE_COMMANDS: Record<string, string[]> = {
  "pnpm-lock.yaml": ["pnpm", "install", "--lockfile-only", "--ignore-scripts"],
  "yarn.lock": ["yarn", "install", "--mode", "update-lockfile"],
  "package-lock.json": ["npm", "install", "--package-lock-only", "--ignore-scripts"],
};

async function regenerateLockfiles(dir: string, conflicted: string[]): Promise<[boolean, string]> {
  const locks = conflicted.filter((f) => basename(f) in LOCKFILE_COMMANDS);
  if (!locks.length) return [true, ""];
  for (const name of locks) {
    if ((await run(["git", "checkout", "--ours", "--", name], { cwd: dir, timeoutMs: 60_000 })).code !== 0) return [false, `could not reset lockfile ${name}`];
    const cmd = LOCKFILE_COMMANDS[basename(name)];
    const r = await run(cmd, { cwd: dir, timeoutMs: 600_000 });
    if (r.code === 127) return [false, `${cmd[0]} is not installed; cannot regenerate ${name}`];
    if (r.code !== 0) return [false, `lockfile regeneration failed for ${name}: ${(r.stderr || r.stdout).trim().slice(0, 300)}`];
    await run(["git", "add", "--", name], { cwd: dir, timeoutMs: 60_000 });
  }
  return [true, "lockfile regenerated"];
}

/** Validate the staged merge result before committing. */
export async function runPostResolutionChecks(dir: string, resolved: string[]): Promise<[boolean, string]> {
  let unresolved = await getConflictedFiles(dir);
  const [lockOk, lockMsg] = await regenerateLockfiles(dir, unresolved);
  if (!lockOk) return [false, lockMsg];
  unresolved = unresolved.filter((f) => !(basename(f) in LOCKFILE_COMMANDS));
  if (unresolved.length) return [false, `Unresolved conflict files remain: ${unresolved.join(", ")}`];
  const dc = await run(["git", "diff", "--cached", "--check", "--", ...resolved], { cwd: dir, timeoutMs: 60_000 });
  if (dc.code !== 0) return [false, `git diff --cached --check failed: ${(dc.stderr || dc.stdout).trim().slice(0, 500)}`];
  const staged = await run(["git", "diff", "--cached", "--quiet"], { cwd: dir, timeoutMs: 60_000 });
  if (staged.code === 0) return [false, "No staged conflict-resolution changes to commit"];
  if (staged.code !== 1) return [false, `Could not inspect staged diff: ${(staged.stderr || staged.stdout).trim().slice(0, 500)}`];
  const checks = ["git diff --cached --check"];
  const py = pythonBin(), pyFiles = resolved.filter((f) => f.endsWith(".py") && existsSync(join(dir, f)) && statSync(join(dir, f)).isFile());
  if (py && pyFiles.length) {
    const pc = await run([py, "-m", "py_compile", ...pyFiles], { cwd: dir, timeoutMs: 120_000 });
    if (pc.code !== 0) return [false, `py_compile failed: ${(pc.stderr || pc.stdout).trim().slice(0, 500)}`];
    checks.push("py_compile");
  }
  if (lockMsg) checks.push(lockMsg);
  return [true, checks.join(", ")];
}

export function stripMarkdownFence(text: string): string {
  text = text.trim();
  const m = /```(?:\w+)?\n([\s\S]*?)\n```/.exec(text);
  return m ? m[1].trim() : text;
}

const free = (xs: string[]) => { const a = [...xs]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
export async function getFreeOpencodeModels(): Promise<string[]> {
  try {
    const r = await run(["opencode", "models"], { timeoutMs: 20_000 });
    if (r.code !== 0) return ["opencode/big-pickle"];
    const models = r.stdout.split(/\r?\n/).map((m) => m.trim()).filter(Boolean).filter((m) => m.endsWith("-free") || m === "opencode/big-pickle");
    if (!models.length) return ["opencode/big-pickle"];
    return models.includes(PREFERRED_FREE_MODEL) ? [PREFERRED_FREE_MODEL, ...free(models.filter((m) => m !== PREFERRED_FREE_MODEL))] : free(models);
  } catch { return ["opencode/big-pickle"]; }
}

const opencodeEnv = () => { const env = scrubEnv(); env.NODE_OPTIONS ??= "--max-old-space-size=2048"; env.NODE_ENV ??= "production"; return env; };
const clean = (s: string) => !!s && !s.includes(MARKER) && !s.includes(">>>>>>>");

/** `[resolvedContent, modelUsed]`; model is "" on failure. */
export async function resolveWithOpencode(content: string): Promise<[string | null, string]> {
  let model = DEFAULT_OPENCODE_MODEL();
  const prompt = `You are resolving a git merge conflict. Return ONLY the final full file content with no markdown fences, no explanations, and no extra text.\n\nFile content with conflict markers:\n${content}`;
  const env = opencodeEnv(), exec = () => run(["opencode", "run", "--model", model, prompt], { env, timeoutMs: opencodeTimeout() * 1000 });
  let r = await exec();
  if (r.code !== 0) {
    const candidates = (await getFreeOpencodeModels()).filter((m) => m !== model);
    if (!candidates.length) return [null, ""];
    model = candidates[Math.floor(Math.random() * candidates.length)];
    r = await exec();
    if (r.code === 0 && r.stdout) {
      const m = /CONTENT:\s*\n```(?:\w+)?\n([\s\S]*?)\n```/.exec(r.stdout);
      if (m && clean(m[1].trim())) return [m[1].trim(), `opencode/${model}`];
      let resolved = stripMarkdownFence(r.stdout);
      if (clean(resolved)) {
        if (resolved.includes("REASONING:") && resolved.includes("```")) resolved = resolved.split("```").at(-2)!.trim();
        return [resolved, `opencode/${model}`];
      }
    }
  }
  if (r.code !== 0) return [null, ""];
  const resolved = stripMarkdownFence(r.stdout || "");
  return !resolved || resolved.includes(MARKER) ? [null, ""] : [resolved, `opencode/${model}`];
}

/** `[resolvedContent, modelLabel]`. */
export async function resolveFileConflictsWithModel(content: string, ai: AIClient | null, provider: string, model: string, preferOpencode = false): Promise<[string | null, string]> {
  if (preferOpencode) { const [r, m] = await resolveWithOpencode(content); if (r) return [r, m]; }
  try {
    if (!ai) return [null, ""];
    if (content.length > hunkThreshold()) {
      const r = await resolveByHunks(content, (snippet, hunk) => ai.resolveConflict(snippet, hunk));
      return r && !r.includes(MARKER) ? [r, `${provider}/${model}`] : [null, ""];
    }
    const r = await ai.resolveConflict(content, content);
    if (r && !r.includes(MARKER)) return [r, `${provider}/${model}`];
  } catch (e: any) { console.log(`AI conflict resolution error: ${e?.message ?? e}`); }
  return [null, ""];
}

async function commitAndPush(dir: string, headBranch: string, files: string[], models: Set<string>, count: number, checks: string): Promise<string> {
  await runGit(["git", "commit", "-m", semanticMessage("fix", "merge", "resolve conflitos de merge")], dir);
  await runGit(["git", ...authConfigArgs(), "push", "origin", headBranch], dir);
  return `Resolved ${count} conflict(s) and pushed\n**Files:** ${files.map((f) => `\`${f}\``).join(", ")}\n**Model/Provider:** ${[...models].sort().join(", ")}\n**Checks:** ${checks}`;
}

export type ConflictOpts = { aiProvider?: string; aiModel?: string; aiConfig?: { apiKey?: string | null; baseUrl?: string | null }; allowAiFallback?: boolean | null; aiClient?: AIClient | null };

/** Resolve merge conflicts in a PR: opencode first (opt-in), AI fallback opt-in via CONFLICT_AI_FALLBACK_ENABLED. `[success, message]`. */
export async function resolveConflictsAutonomously(pr: PR, o: ConflictOpts = {}): Promise<[boolean, string]> {
  const provider = process.env.CONFLICT_AI_PROVIDER ?? o.aiProvider ?? "ollama", model = process.env.CONFLICT_AI_MODEL ?? o.aiModel ?? DEFAULT_OLLAMA_MODEL;
  const allow = o.allowAiFallback ?? truthy("CONFLICT_AI_FALLBACK_ENABLED");
  let ai: AIClient | null = o.aiClient ?? null;
  if (ai === null && allow) { try { ai = getAiClient(provider, { model, ...(o.aiConfig ?? {}) }); } catch { /* fallback unavailable */ } }
  const baseBranch = pr.base.ref, headBranch = pr.head.ref;
  const headClone = githubCloneUrl(pr.head.repo.full_name), baseClone = githubCloneUrl(pr.base.repo.full_name);
  const tmp = mkdtempSync(join(tmpdir(), "conflict-"));
  try {
    // depth=100 captures common ancestors; --depth=1 fails with "unrelated histories" when branches diverged beyond the shallow history.
    const dir = await setupCloneEnvironment(tmp, headClone);
    const [rc, stderr, conflicted] = await tryMergeBase(dir, baseClone, headBranch, baseBranch);
    if (rc === 0) return [true, "No conflicts found during merge"];
    if (rc === -1) {
      if (stderr.includes("refusing to merge unrelated histories")) return [false, `Branches have truly unrelated histories: ${stderr}`];
      if (stderr.includes("no merge base")) return [false, `No common merge base: ${stderr}`];
      return [false, `Merge failed after unshallow: ${stderr}`];
    }
    if (!conflicted.length) return [false, `Merge failed for unknown reason (no conflicted files detected): ${stderr}`];
    // Hundreds of conflicted files cost hours of model calls and starve the rest of the run; that is a rebase for a human.
    const max = maxConflictedFiles();
    if (conflicted.length > max) return [false, `Too many conflicted files (${conflicted.length} > ${max}) — needs a manual rebase`];
    let count = 0; const files: string[] = [], models = new Set<string>();
    for (const file of conflicted) {
      const full = join(dir, file);
      if (!existsSync(full)) continue;
      const content = readFileSync(full, "utf8");
      if (!content.includes(MARKER)) { await runGit(["git", "add", file], dir); count++; files.push(file); models.add("git-auto"); continue; }
      const [resolved, used] = await resolveFileConflictsWithModel(content, ai, provider, model, opencodeConflictEnabled());
      if (resolved) {
        // The resolved content must hit the worktree and the index, otherwise the markers survive and the post-checks abort.
        writeFileSync(full, resolved); await runGit(["git", "add", file], dir);
        count++; files.push(file); models.add(used);
      }
    }
    if (!count) return [false, "AI could not resolve any conflicts"];
    const [ok, checks] = await runPostResolutionChecks(dir, files);
    if (!ok) return [false, checks];
    const [built, build] = await runProjectChecks(dir);
    if (!built) return [false, `Merge resolution not pushed: ${build}`];
    return [true, await commitAndPush(dir, headBranch, files, models, count, `${checks}, ${build}`)];
  } catch (e: any) {
    if (e instanceof GitCommandError) return [false, e.timedOut ? `Conflict resolution timed out: ${safeCmd(e.cmd)}` : `Git command failed: ${safeCmd(e.cmd)} — ${redact(e.stderr || "")}`];
    return [false, "Error resolving conflicts"];
  } finally { rmSync(tmp, { recursive: true, force: true }); }
}
