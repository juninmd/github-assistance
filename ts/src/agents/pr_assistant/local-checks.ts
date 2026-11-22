/**
 * Substitute CI for PRs whose Actions never ran (billing-blocked or repo without CI): clone the exact head SHA and run the
 * project's own build/test gate. Environment problems are reported as skipped (never a red result); a real failure blocks.
 * `MERGE_LOCAL_CHECKS_ENABLED` (default true).
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { PR } from "../../github/client.ts";
import { enabled } from "./review-flags.ts";
import { runProjectChecks } from "./build-check.ts";
import { clonePrHead } from "./review-workspace.ts";
import { run } from "../../utils/proc.ts";
import { scrubEnv } from "../../utils/secure-git.ts";

export type LocalChecks = (pr: PR) => Promise<[boolean, string]>;
export const localChecksEnabled = () => enabled("MERGE_LOCAL_CHECKS_ENABLED", true);

export const runLocalChecks: LocalChecks = async (pr) => {
  if (!localChecksEnabled()) return [true, "checks locais desligados"];
  const token = process.env.GITHUB_TOKEN || process.env.GH_PAT || "";
  if (!token) return [true, "checks locais não executados (sem token)"];
  const tmp = mkdtempSync(join(tmpdir(), "pr-local-checks-"));
  try {
    let dir: string;
    try { dir = await clonePrHead(pr, tmp, token); } catch { return [true, "checks locais não executados (clone falhou)"]; }
    const head = (await run(["git", "rev-parse", "HEAD"], { cwd: dir, timeoutMs: 30_000 })).stdout.trim();
    if (head && pr.head?.sha && head !== pr.head.sha) return [false, `local_checks_sha_mismatch: clonado ${head.slice(0, 8)}, esperado ${String(pr.head.sha).slice(0, 8)}`];
    // PR code runs here (build scripts, conftest, build.rs): never with the bot's tokens or model keys in its environment.
    const env = scrubEnv(); delete env.LITELLM_API_KEY; // scrubEnv keeps the LiteLLM key for opencode; PR code gets none
    const [ok, msg] = await runProjectChecks(dir, env);
    return ok ? [true, msg] : [false, `local_checks_failed: ${msg}`];
  } finally { rmSync(tmp, { recursive: true, force: true }); }
};
