/**
 * Autonomous GitHub Actions pipeline fixing: clone the head branch, feed the real error logs to opencode, validate the edit
 * (checks + independent review) and push. Attempts are tracked across runs via a marker comment.
 */
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { PR } from "../../github/client.ts";
import { run } from "../../utils/proc.ts";
import { scanClone } from "../../utils/secret-scan.ts";
import { authConfigArgs, githubCloneUrl, scrubEnv } from "../../utils/secure-git.ts";
import { semanticMessage } from "../core/commit-message.ts";
import { runProjectChecks } from "./build-check.ts";
import { churnReason } from "./fix-churn.ts";
import { literalReason } from "./fix-literals.ts";
import { forbiddenPaths, generatedPaths, isForbiddenPath, pruneUntrackedForbidden } from "./forbidden-paths.ts";
import { getFreeOpencodeModels, opencodeCmd, setupCloneEnvironment } from "./conflict-resolver.ts";
import { GitCommandError, pythonBin, redact, runGit, safeCmd } from "./git.ts";
import { cloudModel } from "./review-models.ts";
import { verifyPendingFix } from "./review-flow.ts";
import type { GithubClient } from "../../github/client.ts";

export const DEFAULT_MAX_ATTEMPTS = 3, DEFAULT_FIX_TIMEOUT = 1200, DEFAULT_FREE_TIMEOUT = 600;
export const MANUAL_PIPELINE_LABEL = "needs-manual-pipeline-fix";
const envInt = (name: string, def: number, min: number) => { const n = parseInt(process.env[name] || "", 10); return Number.isNaN(n) ? def : Math.max(min, n || def); };
export const fixTimeout = () => envInt("PIPELINE_FIX_TIMEOUT", DEFAULT_FIX_TIMEOUT, 60);
export const freeTimeout = () => envInt("PIPELINE_FIX_FREE_TIMEOUT", DEFAULT_FREE_TIMEOUT, 30);
/** Free opencode models (shuffled), followed by the cloud/auto fallback. */
export async function fixModels(): Promise<string[]> {
  const models = (await getFreeOpencodeModels()).slice(0, envInt("PIPELINE_FIX_MAX_FREE_MODELS", 2, 0));
  const cloud = cloudModel();
  if (!models.includes(cloud)) models.push(cloud);
  return models;
}
const modelTimeout = (m: string) => (m === cloudModel() ? fixTimeout() : freeTimeout());
const MARKER_RE = /<!--\s*pipeline-fix\s+attempt=(\d+)\s+sha=([0-9a-fA-F]+)\s*-->/;
export const pipelineFixEnabled = () => ["1", "true", "yes", "on"].includes((process.env.PIPELINE_FIX_ENABLED ?? "").toLowerCase());
export function maxAttempts(): number { const n = parseInt(process.env.PIPELINE_FIX_MAX_ATTEMPTS ?? String(DEFAULT_MAX_ATTEMPTS), 10); return Number.isNaN(n) ? DEFAULT_MAX_ATTEMPTS : Math.max(1, n); }
export const buildMarker = (attempt: number, sha: string) => `<!-- pipeline-fix attempt=${attempt} sha=${sha} -->`;
/** [last_attempt, last_sha] from the most recent marker comment. */
export function readAttemptState(comments: { body?: string | null }[]): [number, string] {
  let attempt = 0, sha = "";
  for (const c of comments) { const m = MARKER_RE.exec(c.body ?? ""); if (m) { attempt = parseInt(m[1]!, 10); sha = m[2]!; } }
  return [attempt, sha];
}
export function buildPrompt(errorLogs: string, failedChecks: string[]): string {
  return "You are an expert software engineer fixing a failing CI pipeline.\n" +
    `The following GitHub Actions checks are failing: ${failedChecks.join(", ") || "unknown checks"}.\n` +
    "Below are the error logs from the failed jobs.\n" +
    "Apply the MINIMAL, SAFE change to the source/config files in this repository so the\n" +
    "pipeline passes. Do not introduce unrelated changes, new features, or disable tests.\n" +
    "Do not bump or pin runner/image/tool versions (e.g. ubuntu-latest -> ubuntu-24.04)\n" +
    "unless the logs prove that exact version is the cause.\n" +
    "Edit the files directly in the working tree.\n\n" + "Error logs:\n" + errorLogs;
}
async function gitLines(dir: string, args: string[]): Promise<string[]> {
  const r = await run(["git", ...args], { cwd: dir, timeoutMs: 30_000 });
  return r.stdout.split(/\r?\n/).map((f) => f.trim()).filter(Boolean);
}
/** Modified tracked files plus new untracked ones (a fix may only add a file). */
export async function changedFiles(dir: string): Promise<string[]> {
  // Untracked deps/env files are pruned before staging, so they must not veto the fix; tracked ones still do.
  const untracked = (await gitLines(dir, ["ls-files", "--others", "--exclude-standard"])).filter((f) => !isForbiddenPath(f));
  const all = [...new Set([...(await gitLines(dir, ["diff", "--name-only"])), ...untracked])];
  return all.filter((f) => f !== "opencode.json");
}
async function discardChanges(dir: string) {
  await run(["git", "reset", "--hard", "HEAD"], { cwd: dir, timeoutMs: 60_000 });
  await run(["git", "clean", "-fd"], { cwd: dir, timeoutMs: 60_000 });
}
export function summarizeOpencodeOutput(text?: string): string {
  const lines = (text ?? "").replace(/\x1b\[[0-9;]*m/g, "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  return lines.slice(-6).join(" | ").slice(0, 500);
}
export type Accept = (dir: string) => Promise<[boolean, string]>;
/** Run opencode agentically; [model used, error]. A model only counts when it changed files and `accept` approves. */
export async function runOpencodeFix(dir: string, prompt: string, accept?: Accept): Promise<[string, string]> {
  let lastError = "";
  const env: Record<string, string | undefined> = scrubEnv();
  env.NODE_OPTIONS ??= "--max-old-space-size=2048";
  env.NODE_ENV ??= "production";
  let feedback = "";
  for (const model of await fixModels()) {
    try {
      const r = await run([opencodeCmd(), "run", "--model", model, prompt + feedback], { cwd: dir, env, timeoutMs: modelTimeout(model) * 1000 });
      if (r.code === 0) {
        if (!(await changedFiles(dir)).length) { lastError = `${model} made no file changes`; continue; }
        if (!accept) return [`opencode/${model}`, ""];
        const [ok, reason] = await accept(dir);
        if (ok) return [`opencode/${model}`, ""];
        lastError = `${model} edit rejected: ${reason}`;
        feedback = `\n\nA PREVIOUS ATTEMPT WAS REJECTED. Fix this and try again:\n${reason.slice(0, 1500)}`;
        await discardChanges(dir);
        continue;
      }
      await discardChanges(dir);
      lastError = `${model} exited ${r.code}: ${summarizeOpencodeOutput((r.stderr || "") + "\n" + (r.stdout || ""))}`;
    } catch (e) { lastError = `${model} failed to execute: ${(e as Error).name}`; await discardChanges(dir); }
  }
  return ["", lastError];
}
/** Lightweight sanity checks on the opencode edit before pushing. */
export async function validateChanges(dir: string, changed: string[], pr?: PR | null): Promise<[boolean, string]> {
  if (pr) {
    const author = pr.user?.login ?? "";
    if (author.endsWith("[bot]") || author.toLowerCase().includes("dependabot")) {
      const wf = changed.filter((f) => f.startsWith(".github/workflows/"));
      if (wf.length) return [false, `Automated fix cannot modify workflows for bot PRs: ${JSON.stringify(wf)}`];
    }
  }
  const banned = forbiddenPaths(changed);
  if (banned.length) return [false, `Automated fix must not commit build artifacts, dependencies, env files or agent instructions: ${JSON.stringify(banned.slice(0, 8))}`];
  const generated = generatedPaths(dir, changed);
  if (generated.length) return [false, `Automated fix must not hand-edit generated files (edit the source and regenerate): ${JSON.stringify(generated.slice(0, 8))}`];
  const churn = await churnReason(dir);
  if (churn) return [false, `Automated fix rejected: ${churn}`];
  const literal = await literalReason(dir);
  if (literal) return [false, `Automated fix rejected: ${literal}`];
  const chk = await run(["git", "diff", "--check"], { cwd: dir, timeoutMs: 60_000 });
  const out = (chk.stdout || chk.stderr || "").trim();
  // Whitespace nits are not worth a rejected fix; only conflict markers are.
  if (chk.code !== 0 && out.includes("conflict marker")) return [false, `git diff --check failed: ${out.slice(0, 300)}`];
  const py = changed.filter((f) => f.endsWith(".py") && existsSync(join(dir, f)));
  const python = pythonBin();
  if (py.length && python) {
    const c = await run([python, "-m", "py_compile", ...py], { cwd: dir, timeoutMs: 120_000 });
    if (c.code !== 0) return [false, `py_compile failed: ${(c.stderr || c.stdout || "").trim().slice(0, 300)}`];
  }
  return [true, "git diff --check" + (py.length && python ? ", py_compile" : "")];
}
/** One pipeline fix attempt via opencode: [success, message, pushed_sha]. */
export async function fixPipelineAutonomously(gh: GithubClient, pr: PR, errorLogs: string, failedChecks: string[], attempt: number, maxAttemptsValue: number): Promise<[boolean, string, string]> {
  if (!errorLogs.trim()) return [false, "No pipeline error logs available to act on", ""];
  if (pr.head.repo.full_name !== pr.base.repo.full_name) return [false, "PR head is a fork — cannot push fixes", ""];
  const head = pr.head.ref;
  const tmp = mkdtempSync(join(tmpdir(), "pipeline-fix-"));
  try {
    const dir = await setupCloneEnvironment(tmp, githubCloneUrl(pr.head.repo.full_name));
    await runGit(["git", "checkout", head], dir);
    const summary: Record<string, string> = {};
    const acceptFix: Accept = async (d) => {
      const changedNow = await changedFiles(d);
      const [valid, checks] = await validateChanges(d, changedNow, pr);
      if (!valid) return [false, checks];
      const [built, build] = await runProjectChecks(d);
      if (!built) return [false, build];
      const [reviewed, review] = await verifyPendingFix(gh, d, pr);
      if (!reviewed) return [false, review];
      summary.changed = changedNow.join(", "); summary.checks = `${checks}, ${build}, ${review}`;
      return [true, ""];
    };
    const [used, err] = await runOpencodeFix(dir, buildPrompt(errorLogs, failedChecks), acceptFix);
    if (!used) return [false, `opencode did not produce a fix${err ? `: ${err}` : ""}`, ""];
    if (!summary.changed) {
      if (!(await changedFiles(dir)).length) return [false, "opencode made no file changes", ""];
      const [ok, reason] = await acceptFix(dir);
      if (!ok) return [false, `Auto-fix not pushed: ${reason}`, ""];
    }
    await pruneUntrackedForbidden(dir);
    await runGit(["git", "add", "-A"], dir);
    const findings = await scanClone(dir);
    if (findings.length) return [false, `Fix not pushed: secret found in ${findings.slice(0, 8).map((h) => `${h.file}:${h.line} -> ${h.rule_id}`).join("; ")}`, ""];
    await runGit(["git", "commit", "-m", semanticMessage("fix", "ci", "corrige falha de pipeline do PR", `Tentativa ${attempt}/${maxAttemptsValue} via ${used}.`)], dir);
    await runGit(["git", ...authConfigArgs(), "push", "origin", head], dir);
    const sha = (await runGit(["git", "rev-parse", "HEAD"], dir)).stdout.trim();
    const files = summary.changed!.split(", ").map((f) => `\`${f}\``).join(", ");
    return [true, `Pushed pipeline fix (attempt ${attempt}/${maxAttemptsValue})\n**Files:** ${files}\n**Model/Provider:** ${used}\n**Checks:** ${summary.checks}`, sha];
  } catch (e) {
    if (e instanceof GitCommandError) return [false, e.timedOut ? `Pipeline fix timed out: ${safeCmd(e.cmd)}` : `Git command failed: ${safeCmd(e.cmd)} — ${redact(e.stderr || "")}`, ""];
    return [false, "Error fixing pipeline", ""];
  } finally { rmSync(tmp, { recursive: true, force: true }); }
}
