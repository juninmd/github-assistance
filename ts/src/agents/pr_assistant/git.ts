/** Git helpers shared by the conflict and pipeline fixers (token-free URLs; auth rides on per-command `-c` args). */
import { run, type RunResult } from "../../utils/proc.ts";
import { redactCmd, redactSecrets } from "../../utils/secure-git.ts";

export class GitCommandError extends Error {
  constructor(public cmd: string[], public code: number, public stderr: string, public timedOut = false) { super(`git command failed (${code})`); }
}
/** Remove tokens and secrets from git output before logging or returning. */
export const redact = (t: string) => redactSecrets(t).trim();
export const safeCmd = (cmd: string[]) => redactCmd(cmd);

/** Network ops on big repos routinely exceed 2 minutes. Merge is expected to fail on conflicts (no throw); everything else must succeed. */
export async function runGit(cmd: string[], cwd: string): Promise<RunResult> {
  const timeoutMs = cmd.some((a) => ["clone", "fetch", "push"].includes(a)) ? 600_000 : 120_000;
  const r = await run(cmd, { cwd, timeoutMs });
  if (r.timedOut) throw new GitCommandError(cmd.map(redactSecrets), 124, "", true);
  if (r.code !== 0 && !cmd.includes("merge")) throw new GitCommandError(cmd.map(redactSecrets), r.code, redact(r.stderr || ""));
  return r;
}

export async function getConflictedFiles(cwd: string): Promise<string[]> {
  const r = await run(["git", "diff", "--name-only", "--diff-filter=U"], { cwd, timeoutMs: 30_000 });
  return r.stdout.split(/\r?\n/).map((f) => f.trim()).filter(Boolean);
}
export const pythonBin = () => Bun.which("python3") ?? Bun.which("python");
