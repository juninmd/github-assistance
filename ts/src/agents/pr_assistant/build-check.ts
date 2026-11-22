/**
 * Build/test gate run on an auto-fix before it is pushed (project's own fast check: pytest, go build, cargo check, npm build/test).
 * Environment problems (tool missing, deps not installed) are *skipped*, never a failed fix, so the gate cannot block on infra.
 * `PR_FIX_VALIDATE`: auto (default) | off; `PR_FIX_VALIDATE_TIMEOUT` bounds each command (seconds, default 300).
 */
import { existsSync, readFileSync, statSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { run } from "../../utils/proc.ts";
import { pythonBin } from "./git.ts";

// Output markers meaning "the environment cannot run this", not "the fix is bad".
const ENV_MARKERS = ["no module named", "command not found", "modulenotfounderror", "cannot find module", "error: no such command", "executable file not found", "no tests ran", "error collecting"];
const TAIL_CHARS = 600;
export const validationMode = () => (["off", "0", "false"].includes((process.env.PR_FIX_VALIDATE ?? "auto").toLowerCase()) ? "off" : "auto");
const timeoutMs = () => { const n = parseInt(process.env.PR_FIX_VALIDATE_TIMEOUT ?? "300", 10); return (Number.isNaN(n) ? 300 : Math.max(30, n)) * 1000; };
const isFile = (p: string) => existsSync(p) && statSync(p).isFile();
const isDir = (p: string) => existsSync(p) && statSync(p).isDirectory();

/** `[label, argv]` checks for the project types found in `cloneDir`. */
export function detectCommands(cloneDir: string): [string, string[]][] {
  const cmds: [string, string[]][] = [], f = (n: string) => join(cloneDir, n);
  if (isFile(f("go.mod")) && Bun.which("go")) cmds.push(["go build", ["go", "build", "./..."]]);
  if (isFile(f("Cargo.toml")) && Bun.which("cargo")) cmds.push(["cargo check", ["cargo", "check", "--quiet"]]);
  if (isFile(f("package.json")) && isDir(f("node_modules")) && Bun.which("npm")) {
    const text = readFileSync(f("package.json"), "utf8");
    for (const script of ["build", "test"]) if (text.includes(`"${script}"`)) { cmds.push([`npm ${script}`, ["npm", "run", script, "--silent"]]); break; }
  }
  const py = pythonBin();
  if (py && isDir(f("tests")) && (isFile(f("pyproject.toml")) || isFile(f("pytest.ini")))) cmds.push(["pytest", [py, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"]]);
  return cmds;
}
const envProblem = (code: number, output: string) => code === 126 || code === 127 || ENV_MARKERS.some((m) => output.toLowerCase().includes(m));

async function untracked(cloneDir: string): Promise<Set<string>> {
  const r = await run(["git", "ls-files", "--others", "--exclude-standard"], { cwd: cloneDir, timeoutMs: 60_000 });
  return new Set(r.stdout.split(/\r?\n/).filter(Boolean));
}

/** Run the project's build/test gate. */
export async function runProjectChecks(cloneDir: string, baseEnv: Record<string, string | undefined> = process.env): Promise<[boolean, string]> {
  if (validationMode() === "off") return [true, "build gate off"];
  const cmds = detectCommands(cloneDir);
  if (!cmds.length) return [true, "build gate skipped (no runnable check)"];
  const before = await untracked(cloneDir), env = { ...baseEnv, PYTHONDONTWRITEBYTECODE: "1", CI: "1" };
  try { return await runAll(cloneDir, cmds, env); }
  finally { for (const rel of await untracked(cloneDir)) if (!before.has(rel)) { try { unlinkSync(join(cloneDir, rel)); } catch { /* best-effort */ } } } // artifacts must never reach the fix commit
}

async function runAll(cloneDir: string, cmds: [string, string[]][], env: Record<string, string | undefined>): Promise<[boolean, string]> {
  const passed: string[] = [], skipped: string[] = [];
  for (const [label, argv] of cmds) {
    const r = await run(argv, { cwd: cloneDir, env, timeoutMs: timeoutMs() });
    if (r.timedOut) { skipped.push(`${label} (TimeoutExpired)`); continue; } // never block on infra
    const output = (r.stdout + r.stderr).trim();
    if (r.code === 0) passed.push(label);
    else if (envProblem(r.code, output)) skipped.push(`${label} (env)`);
    else return [false, `${label} failed: ${output.slice(-TAIL_CHARS)}`];
  }
  const parts: string[] = [];
  if (passed.length) parts.push("build gate passed: " + passed.join(", "));
  if (skipped.length) parts.push("skipped: " + skipped.join(", "));
  return [true, parts.join("; ") || "build gate skipped"];
}
