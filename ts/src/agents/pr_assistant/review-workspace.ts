/** Ephemeral clone + opencode execution for the advisory PR code review (shallow, temp, always removed). */
import { mkdirSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DEFAULT_LITELLM_API_BASE } from "../../config/settings.ts";
import { recordTrace } from "../../insight/cost.ts";
import { availableSkills, harnessVersion, parseEvents, type RunTrace } from "../opencode/trace.ts";
import * as tokenix from "../../utils/tokenix.ts";
import { getLogger } from "../../utils/logger.ts";
import { run } from "../../utils/proc.ts";
import { freeExhausted, isFreeModel, isFreeQuotaError, markFreeExhausted } from "./review-models.ts";
import { authConfigArgs, githubCloneUrl } from "../../utils/secure-git.ts";

const log = getLogger("review");
/** One-line failure detail for logs, with any token scrubbed. */
export const brief = (s: string) => {
  let t = (s || "").replace(/\s+/g, " ").trim().slice(-300);
  for (const k of [process.env.GITHUB_TOKEN, process.env.GH_PAT, process.env.LITELLM_API_KEY]) if (k) t = t.split(k).join("***");
  return t;
};
export const DEFAULT_MODEL = "litellm/cloud/auto";
export const CLONE_TIMEOUT = 120_000;
export const STALE_AGE_SECONDS = 7200;
export const REVIEW_PREFIX = "pr-review-";
export const DEFAULT_TIMEOUT = 300;
export const DEFAULT_DEADLINE = 900;
// Total wall-clock budget for one PR review: models x packages x 300s would otherwise run for hours.
let deadlineAt = 0;
export function startDeadline(now = Date.now()): void {
  const n = parseInt(process.env.OPENCODE_REVIEW_DEADLINE || "", 10);
  deadlineAt = now + (Number.isNaN(n) || !n ? DEFAULT_DEADLINE : n) * 1000;
}
export const clearDeadline = () => { deadlineAt = 0; };
export const deadlineLeftSec = (now = Date.now()) => deadlineAt ? Math.floor((deadlineAt - now) / 1000) : Infinity;

export const opencodeCmd = () => Bun.which("opencode") ?? "opencode";
export function reviewTimeout(): number {
  const n = parseInt(process.env.OPENCODE_REVIEW_TIMEOUT || "", 10);
  return Number.isNaN(n) || !n ? DEFAULT_TIMEOUT : n;
}
export const reviewModel = () => process.env.OPENCODE_REVIEW_MODEL || DEFAULT_MODEL;
export function litellmBase(): string {
  const base = (process.env.LITELLM_API_BASE ?? DEFAULT_LITELLM_API_BASE).replace(/\/+$/, "");
  return base.endsWith("/v1") ? base : `${base}/v1`;
}
export function cleanupStaleReviewDirs(root = tmpdir()): void {
  const now = Date.now() / 1000;
  let names: string[] = [];
  try { names = readdirSync(root).filter((n) => n.startsWith(REVIEW_PREFIX)); } catch { return; }
  for (const n of names) {
    try { const p = join(root, n); const st = statSync(p); if (st.isDirectory() && now - st.mtimeMs / 1000 > STALE_AGE_SECONDS) rmSync(p, { recursive: true, force: true }); } catch { /* skip */ }
  }
}
/**
 * Shallow-clone the PR head branch (token rides on -c args, never in the remote URL). `origin/<base>` is pinned to the
 * merge-base when known, so every diff against it is the PR's own change even when the PR is behind its base.
 */
export async function clonePrHead(pr: any, tmpdirPath: string, token: string, mergeBase = ""): Promise<string> {
  const dest = join(tmpdirPath, "repo");
  const c = await run(["git", ...authConfigArgs(token), "clone", "--depth=1", "--single-branch", "--branch", pr.head.ref, githubCloneUrl(pr.head.repo.full_name), dest], { timeoutMs: CLONE_TIMEOUT });
  if (c.code !== 0) throw new Error(`review clone failed: ${brief(c.stderr)}`);
  const fetchBase = (src: string) => run(["git", ...authConfigArgs(token), "fetch", "--depth=1", "origin", `+${src}:refs/remotes/origin/${pr.base.ref}`], { cwd: dest });
  if (!mergeBase || (await fetchBase(mergeBase)).code !== 0) await fetchBase(pr.base.ref);
  return dest;
}
/** Diff against the base; `includeWorktree` also covers uncommitted (unpushed) fixes. */
export async function localDiff(cloneDir: string, baseRef: string, maxChars: number, includeWorktree = false): Promise<string> {
  let args: string[];
  if (includeWorktree) { await run(["git", "add", "-A"], { cwd: cloneDir, timeoutMs: 60_000 }); args = ["git", "diff", "--cached", "--unified=3", `origin/${baseRef}`]; }
  else args = ["git", "diff", "--unified=3", `origin/${baseRef}`, "HEAD"];
  return (await run(args, { cwd: cloneDir, timeoutMs: 60_000 })).stdout.slice(0, maxChars);
}
/** opencode config dir pointing at the LiteLLM proxy (outside the clone so it is never committed). */
export function writeOpencodeConfig(configDir: string): void {
  const config = {
    $schema: "https://opencode.ai/config.json",
    provider: { litellm: { npm: "@ai-sdk/openai-compatible", name: "LiteLLM",
      options: { baseURL: litellmBase(), apiKey: "{env:LITELLM_API_KEY}" }, models: { "cloud/auto": { name: "cloud/auto" } } } },
  };
  mkdirSync(configDir, { recursive: true });
  writeFileSync(join(configDir, "opencode.json"), JSON.stringify(config, null, 2) + "\n", "utf8");
}
let lastTraceValue: RunTrace | null = null;
export const resetTrace = () => { lastTraceValue = null; };
export const lastTrace = () => lastTraceValue;

/** Run opencode non-interactively; assistant text, or null on any failure. */
export async function runOpencode(cloneDir: string, prompt: string, model: string, timeoutSec: number): Promise<string | null> {
  const env: Record<string, string | undefined> = { ...process.env };
  env.NODE_OPTIONS ??= "--max-old-space-size=1536";
  env.NODE_ENV ??= "production";
  let result; let on = false;
  const left = deadlineLeftSec();
  if (left < 30) { log.warning(`opencode skipped (${model}): review deadline reached`); return null; }
  timeoutSec = Math.min(timeoutSec, left);
  if (isFreeModel(model) && freeExhausted()) return null; // account quota already spent: don't pay a doomed call per model
  try {
    result = await tokenix.session(cloneDir, async (ready) => {
      on = ready;
      return run([opencodeCmd(), "run", "--format", "json", "--model", model, prompt], { cwd: cloneDir, timeoutMs: timeoutSec * 1000, env });
    });
  } catch (e) { log.warning(`opencode failed (${model}): ${brief(String((e as Error)?.message ?? e))}`); return null; }
  if (result.code !== 0 && isFreeModel(model) && isFreeQuotaError(result.stderr || result.stdout)) markFreeExhausted();
  if (result.code !== 0) { log.warning(`opencode exit ${result.code}${result.timedOut ? " (timeout)" : ""} (${model}): ${brief(result.stderr || result.stdout)}`); return null; }
  const [text, facts] = parseEvents(result.stdout);
  const version = await harnessVersion(opencodeCmd());
  lastTraceValue = { harness: `opencode ${version}`.trim() + tokenix.harnessSuffix(on), model, skills_available: availableSkills([cloneDir]), ...facts };
  recordTrace(lastTraceValue);
  return text;
}
