/**
 * The owner's agent contract: global AGENTS.md + skills from juninmd/skills, refreshed to the newest commit before
 * opencode runs (opencode auto-loads ~/.config/opencode/{AGENTS.md,skills}). Fail-open: on any error the copy already
 * installed (baked into the image) stays in use and the run continues.
 */
import { cpSync, existsSync, mkdirSync, renameSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { run } from "../../utils/proc.ts";
import { scrubEnv } from "../../utils/secure-git.ts";

export const SKILLS_REPO = "https://github.com/juninmd/skills";
export type Contract = { sha: string | null; source: "fresh" | "cache" | "disabled" };
type Log = (m: string, level?: string) => void;
type Runner = typeof run;

const truthy = (v: string | undefined, d: boolean) => (v === undefined || v.trim() === "" ? d : ["1", "true", "yes", "on"].includes(v.trim().toLowerCase()));
/** Off by default: it replaces ~/.config/opencode/skills, so only the image (Dockerfile ENV) turns it on, never a dev machine. */
export const contractEnabled = () => truthy(process.env.AGENT_CONTRACT_REFRESH, false);
const ttlMs = () => Math.max(1, parseInt(process.env.AGENT_CONTRACT_TTL_MINUTES ?? "", 10) || 60) * 60_000;

let state: (Contract & { at: number }) | null = null;
let inflight: Promise<Contract> | null = null;
export const resetContract = () => { state = null; inflight = null; };
export const currentContract = (): Contract | null => (state ? { sha: state.sha, source: state.source } : null);
/** Short label for PR bodies and review footers, e.g. `juninmd/skills@1a2b3c4`. */
export const contractLabel = () => (state?.sha ? `juninmd/skills@${state.sha.slice(0, 7)}` : "");

async function git(args: string[], r: Runner, cwd?: string): Promise<string> {
  // Public repository: no credentials, no prompts.
  const res = await r(["git", ...args], { cwd, timeoutMs: 120_000, env: { ...scrubEnv(), GIT_TERMINAL_PROMPT: "0" } });
  if (res.code !== 0 || res.timedOut) throw new Error(`git ${args[0]} failed: ${(res.stderr || "").trim().slice(0, 200)}`);
  return res.stdout.trim();
}

/** Swap the installed skills/AGENTS.md for the fetched ones; skills removed upstream disappear too. */
function install(src: string, home: string): void {
  const cfg = join(home, ".config", "opencode"), skills = join(cfg, "skills"), fresh = `${skills}.new`, old = `${skills}.old`;
  mkdirSync(cfg, { recursive: true });
  rmSync(fresh, { recursive: true, force: true }); rmSync(old, { recursive: true, force: true });
  cpSync(join(src, ".agents", "skills"), fresh, { recursive: true });
  if (existsSync(skills)) renameSync(skills, old);
  renameSync(fresh, skills);
  rmSync(old, { recursive: true, force: true });
  cpSync(join(src, ".agents", "AGENTS.md"), join(cfg, "AGENTS.md"));
}

export function ensureContract(log: Log, o: { home?: string; runner?: Runner; now?: number } = {}): Promise<Contract> {
  if (!contractEnabled()) return Promise.resolve({ sha: null, source: "disabled" });
  const now = o.now ?? Date.now();
  if (state && now - state.at < ttlMs()) return Promise.resolve(currentContract()!);
  // Concurrent PR workers share one refresh instead of racing git in the same directory.
  return (inflight ??= refresh(log, now, o.home ?? homedir(), o.runner ?? run).finally(() => { inflight = null; }));
}

async function refresh(log: Log, now: number, home: string, r: Runner): Promise<Contract> {
  const cache = join(home, ".cache", "github-assistance", "skills");
  try {
    if (existsSync(join(cache, ".git"))) {
      await git(["fetch", "--depth", "1", "origin", "HEAD"], r, cache);
      await git(["reset", "--hard", "FETCH_HEAD"], r, cache);
    } else {
      rmSync(cache, { recursive: true, force: true }); mkdirSync(join(cache, ".."), { recursive: true });
      await git(["clone", "--depth", "1", SKILLS_REPO, cache], r);
    }
    const sha = await git(["rev-parse", "HEAD"], r, cache);
    install(cache, home);
    state = { sha, source: "fresh", at: now };
    log(`Agent contract refreshed: juninmd/skills@${sha.slice(0, 7)}`);
  } catch (e: any) {
    log(`Agent contract refresh failed, keeping the installed copy: ${e?.message ?? e}`, "WARNING");
    state = { sha: state?.sha ?? null, source: "cache", at: now };
  }
  return currentContract()!;
}
