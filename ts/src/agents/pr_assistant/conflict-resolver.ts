/** Autonomous merge conflict resolution for PR Assistant (clone → merge base → classify → resolve block by block → validate → push). */
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { getAiClient, type AIClient } from "../../ai/client.ts";
import { DEFAULT_OLLAMA_MODEL } from "../../config/settings.ts";
import type { PR } from "../../github/client.ts";
import { run } from "../../utils/proc.ts";
import { authConfigArgs, githubCloneUrl, scrubEnv } from "../../utils/secure-git.ts";
import { semanticMessage } from "../core/commit-message.ts";
import { DEFAULT_OPENCODE_MODEL } from "../core/utils.ts";
import { PREFERRED_FREE_MODEL } from "../opencode/models.ts";
import { gitIdentity } from "./bot-identity.ts";
import { runProjectChecks } from "./build-check.ts";
import { cleanAnswer, hasMarkers, resolveHunks } from "./conflict-hunks.ts";
import { LOCKFILE_COMMANDS, canRegenerate, conflictKinds, conflictPrompt, isLockfile, workflowPushBlocked, type ConflictInfo } from "./conflict-plan.ts";
import { getConflictedFiles, GitCommandError, pythonBin, redact, runGit, safeCmd } from "./git.ts";

const OPENCODE_RESOLUTION_TIMEOUT = 600, DEFAULT_MAX_CONFLICTED_FILES = 20;
export { LOCKFILE_COMMANDS };
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
  const who = gitIdentity();
  await runGit(["git", "config", "user.email", who.email], dir);
  await runGit(["git", "config", "user.name", who.name], dir);
  return dir;
}

/** Attempt the merge, retrying with a full clone if the shallow depth is insufficient. `[rc, stderr, conflicted]`; rc -1 = unrelated histories. */
export async function tryMergeBase(dir: string, baseClone: string, headBranch: string, baseBranch: string): Promise<[number, string, string[]]> {
  await runGit(["git", "checkout", headBranch], dir);
  await runGit(["git", "remote", "add", "upstream", baseClone], dir);
  await runGit(["git", ...authConfigArgs(), "fetch", "--depth=100", "upstream", baseBranch], dir);
  // zdiff3 puts the common ancestor inside each conflict, which is what lets a block be resolved without guessing.
  let style = "zdiff3";
  const merge = (timeoutMs: number) => run(["git", "-c", `merge.conflictStyle=${style}`, "merge", `upstream/${baseBranch}`], { cwd: dir, timeoutMs });
  let m = await merge(120_000);
  if (m.code !== 0 && /conflictstyle|zdiff3/i.test(m.stderr)) { style = "diff3"; m = await merge(120_000); } // git < 2.35
  let stderr = m.stderr.trim();
  if (m.code === 0) return [0, stderr, []];
  if (stderr.includes("fatal: refusing to merge unrelated histories") || stderr.includes("fatal: no merge base")) {
    await runGit(["git", ...authConfigArgs(), "fetch", "--unshallow"], dir);
    m = await merge(300_000);
    stderr = m.stderr.trim();
    if (m.code !== 0 && (stderr.includes("fatal: refusing to merge unrelated histories") || stderr.includes("fatal: no merge base"))) return [-1, stderr, []];
  }
  return [m.code, stderr, await getConflictedFiles(dir)];
}

async function regenerateLockfiles(dir: string, conflicted: string[]): Promise<[boolean, string]> {
  const locks = conflicted.filter(canRegenerate);
  if (!locks.length) return [true, ""];
  for (const name of locks) {
    if ((await run(["git", "checkout", "--ours", "--", name], { cwd: dir, timeoutMs: 60_000 })).code !== 0) return [false, `could not reset lockfile ${name}`];
    const cmd = LOCKFILE_COMMANDS[basename(name)]!;
    const r = await run(cmd, { cwd: dirname(join(dir, name)), timeoutMs: 600_000 });
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
  unresolved = unresolved.filter((f) => !canRegenerate(f));
  if (unresolved.length) return [false, `Unresolved conflict files remain: ${unresolved.join(", ")}`];
  // Leftover markers are the real danger; `git diff --check` also failed on harmless trailing whitespace the base brought in.
  const marked = resolved.filter((f) => existsSync(join(dir, f)) && statSync(join(dir, f)).isFile() && hasMarkers(readFileSync(join(dir, f), "utf8")));
  if (marked.length) return [false, `Conflict markers remain in: ${marked.join(", ")}`];
  const staged = await run(["git", "diff", "--cached", "--quiet"], { cwd: dir, timeoutMs: 60_000 });
  if (staged.code === 0) return [false, "No staged conflict-resolution changes to commit"];
  if (staged.code !== 1) return [false, `Could not inspect staged diff: ${(staged.stderr || staged.stdout).trim().slice(0, 500)}`];
  const checks = ["no conflict markers"];
  const py = pythonBin(), pyFiles = resolved.filter((f) => f.endsWith(".py") && existsSync(join(dir, f)) && statSync(join(dir, f)).isFile());
  if (py && pyFiles.length) {
    const pc = await run([py, "-m", "py_compile", ...pyFiles], { cwd: dir, timeoutMs: 120_000 });
    if (pc.code !== 0) return [false, `py_compile failed: ${(pc.stderr || pc.stdout).trim().slice(0, 500)}`];
    checks.push("py_compile");
  }
  if (lockMsg) checks.push(lockMsg);
  return [true, checks.join(", ")];
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
type Asker = { label: string; ask: (prompt: string) => Promise<string | null> };
/** opencode with the default model, then one free model; the label is the model that answered. */
function opencodeAsker(): Asker {
  const asker: Asker = { label: "opencode", ask: async (prompt) => {
    const env = opencodeEnv();
    const models = [DEFAULT_OPENCODE_MODEL(), ...(await getFreeOpencodeModels())].filter((m, i, a) => a.indexOf(m) === i).slice(0, 2);
    for (const model of models) {
      const r = await run([opencodeCmd(), "run", "--model", model, prompt], { env, timeoutMs: opencodeTimeout() * 1000 });
      if (r.code === 0 && r.stdout.trim()) { asker.label = `opencode/${model}`; return r.stdout; }
    }
    return null;
  } };
  return asker;
}
const GENERIC: ConflictInfo = { file: "(arquivo)", title: "", head: "HEAD", base: "base" };
/**
 * `[resolvedContent, modelLabel]`. Block by block: trivial blocks are settled without a model; the others go to opencode
 * (when preferred) and then to the AI client. Any block nobody can merge safely fails the whole file.
 */
export async function resolveFileConflictsWithModel(content: string, ai: AIClient | null, provider: string, model: string, preferOpencode = false, info: ConflictInfo = GENERIC): Promise<[string | null, string]> {
  const askers: Asker[] = [...(preferOpencode ? [opencodeAsker()] : []), ...(ai ? [{ label: `${provider}/${model}`, ask: (p: string) => ai.generate(p) }] : [])];
  const used = new Set<string>();
  try {
    const r = await resolveHunks(content, async (c) => {
      const prompt = conflictPrompt(info, c);
      for (const a of askers) {
        let answer: string | null = null;
        try { answer = await a.ask(prompt); } catch { /* next asker */ }
        if (cleanAnswer(answer, c.hunk, c.pre, c.post, "\n")) { used.add(a.label); return answer; }
      }
      return null;
    });
    if (!r || hasMarkers(r.text)) return [null, ""];
    if (r.auto) used.add("git-auto");
    return [r.text, [...used].sort().join(", ")];
  } catch (e: any) { console.log(`AI conflict resolution error: ${e?.message ?? e}`); return [null, ""]; }
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
    // Everything that cannot be merged safely is decided before the first model call.
    const kinds = await conflictKinds(dir);
    if (kinds.structural.length) return [false, `manual-delete-add: um lado removeu, renomeou ou criou ${kinds.structural.map((f) => `\`${f}\``).join(", ")}; isso é uma decisão, não um merge`];
    const orphanLocks = conflicted.filter((f) => isLockfile(f) && !canRegenerate(f));
    if (orphanLocks.length) return [false, `Lockfile sem regeneração automática: ${orphanLocks.join(", ")}; regenere com a ferramenta do ecossistema`];
    const pushBlocked = await workflowPushBlocked(dir, baseBranch);
    if (pushBlocked) return [false, pushBlocked];
    let count = 0; const files: string[] = [], models = new Set<string>();
    for (const file of conflicted.filter((f) => !isLockfile(f))) {
      const full = join(dir, file);
      const content = existsSync(full) ? readFileSync(full, "utf8") : "";
      // No markers in an unmerged file means a binary or mode conflict: staging it would silently keep one side.
      if (!hasMarkers(content) || content.includes("\0")) return [false, `\`${file}\` está em conflito sem marcadores de texto (binário ou modo); escolha um dos lados manualmente`];
      const [resolved, used] = await resolveFileConflictsWithModel(content, ai, provider, model, opencodeConflictEnabled(), { file, title: pr.title ?? "", head: headBranch, base: baseBranch });
      if (!resolved) return [false, `Não foi possível resolver \`${file}\` com segurança (${count} arquivo(s) resolvidos antes dele; nada foi enviado)`];
      // The resolved content must hit the worktree and the index, otherwise the markers survive and the post-checks abort.
      writeFileSync(full, resolved); await runGit(["git", "add", file], dir);
      count++; files.push(file); used.split(", ").filter(Boolean).forEach((m) => models.add(m));
    }
    const locks = conflicted.filter(canRegenerate);
    if (!count && !locks.length) return [false, "AI could not resolve any conflicts"];
    if (locks.length) { count += locks.length; models.add("lockfile-regen"); }
    const [ok, checks] = await runPostResolutionChecks(dir, files);
    files.push(...locks);
    if (!ok) return [false, checks];
    const [built, build] = await runProjectChecks(dir);
    if (!built) return [false, `Merge resolution not pushed: ${build}`];
    return [true, await commitAndPush(dir, headBranch, files, models, count, `${checks}, ${build}`)];
  } catch (e: any) {
    if (e instanceof GitCommandError) return [false, e.timedOut ? `Conflict resolution timed out: ${safeCmd(e.cmd)}` : `Git command failed: ${safeCmd(e.cmd)} — ${redact(e.stderr || "")}`];
    return [false, "Error resolving conflicts"];
  } finally { rmSync(tmp, { recursive: true, force: true }); }
}
