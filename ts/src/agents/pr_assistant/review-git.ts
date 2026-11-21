/** Commit and push review fixes back to the PR head branch (best-effort; never throws). */
import { run } from "../../utils/proc.ts";
import { scanClone } from "../../utils/secret-scan.ts";
import { authConfigArgs } from "../../utils/secure-git.ts";
import { churnReason } from "./fix-churn.ts";
import { literalReason } from "./fix-literals.ts";
import { forbiddenPaths, generatedPaths, pruneUntrackedForbidden } from "./forbidden-paths.ts";

const GIT_TIMEOUT = 120_000;
const git = (args: string[], cwd: string, timeoutMs = GIT_TIMEOUT) => run(["git", ...args], { cwd, timeoutMs });

/** Apply a unified diff; false when it does not apply cleanly. */
export async function applyPatch(cloneDir: string, patch: string): Promise<boolean> {
  if (!patch.trim()) return false;
  try { return (await run(["git", "apply", "--whitespace=fix", "-"], { cwd: cloneDir, input: patch, timeoutMs: 60_000 })).code === 0; }
  catch { return false; }
}
export async function discardChanges(cloneDir: string): Promise<void> {
  try { await git(["reset", "--hard", "HEAD"], cloneDir, 60_000); await git(["clean", "-fd"], cloneDir, 60_000); } catch { /* best-effort */ }
}
/** Stage, commit and push to `headRef`; returns [ok, sha-or-detail]. */
export async function commitAndPush(cloneDir: string, headRef: string, message: string): Promise<[boolean, string]> {
  try {
    await pruneUntrackedForbidden(cloneDir);
    await git(["add", "-A"], cloneDir, 60_000);
    await git(["rm", "--cached", "--ignore-unmatch", "opencode.json"], cloneDir, 30_000);
    const staged = await git(["diff", "--cached", "--quiet"], cloneDir, 30_000);
    if (staged.code !== 1) return [false, ""];
    const names = (await git(["diff", "--cached", "--name-only"], cloneDir, 30_000)).stdout.split("\n").filter(Boolean);
    const banned = forbiddenPaths(names);
    if (banned.length) return [false, "forbidden-path: " + banned.slice(0, 8).join("; ")];
    const generated = generatedPaths(cloneDir, names);
    if (generated.length) return [false, "generated-file: " + generated.slice(0, 8).join("; ")];
    const churn = await churnReason(cloneDir, true);
    if (churn) return [false, "whitespace-churn: " + churn];
    const literal = await literalReason(cloneDir, true);
    if (literal) return [false, "template-literal: " + literal];
    const findings = await scanClone(cloneDir);
    if (findings.length) return [false, "secret-found: " + findings.slice(0, 8).map((h) => `${h.file}:${h.line} -> ${h.rule_id}`).join("; ")];
    const c = await git(["-c", "user.email=github-assistance@github.com", "-c", "user.name=github-assistance", "commit", "-m", message], cloneDir, 60_000);
    if (c.code !== 0) return [false, ""];
    // `-c` must precede the subcommand (`git push -c …` is invalid; the Python original had it in that order).
    const p = await git([...authConfigArgs(process.env.GITHUB_TOKEN), "push", "origin", `HEAD:${headRef}`], cloneDir);
    if (p.code !== 0) return [false, ""];
    return [true, (await git(["rev-parse", "HEAD"], cloneDir, 30_000)).stdout.trim()];
  } catch { return [false, ""]; }
}
