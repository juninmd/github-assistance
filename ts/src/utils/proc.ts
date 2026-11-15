/** Subprocess runner that kills the whole process group on timeout (no orphaned grandchildren). */
export type RunOpts = { cwd?: string; env?: Record<string, string | undefined>; input?: string; timeoutMs?: number };
export type RunResult = { code: number; stdout: string; stderr: string; timedOut: boolean };

export async function run(cmd: string[], o: RunOpts = {}): Promise<RunResult> {
  const env: Record<string, string | undefined> = { ...(o.env ?? process.env) };
  // Some tools (opencode) resolve the project from $PWD rather than the process cwd.
  if (o.cwd) env.PWD = o.cwd;
  let proc: ReturnType<typeof Bun.spawn>;
  try {
    proc = Bun.spawn(cmd, { cwd: o.cwd, env: env as any, stdin: o.input !== undefined ? new TextEncoder().encode(o.input) : "ignore", stdout: "pipe", stderr: "pipe" });
  } catch (e: any) {
    return { code: 127, stdout: "", stderr: String(e?.message ?? e), timedOut: false };
  }
  let timedOut = false;
  const timer = o.timeoutMs ? setTimeout(() => { timedOut = true; killTree(proc.pid); }, o.timeoutMs) : null;
  const [stdout, stderr] = await Promise.all([new Response(proc.stdout as ReadableStream).text(), new Response(proc.stderr as ReadableStream).text()]);
  const code = await proc.exited;
  if (timer) clearTimeout(timer);
  return { code: timedOut ? 124 : code, stdout, stderr, timedOut };
}

function killTree(pid: number): void {
  // Children inherit the pgid only when spawned detached; fall back to pid kill plus pkill of children.
  try { process.kill(-pid, "SIGKILL"); return; } catch { /* not a group leader */ }
  try { Bun.spawnSync(["pkill", "-KILL", "-P", String(pid)]); } catch { /* ignore */ }
  try { process.kill(pid, "SIGKILL"); } catch { /* gone */ }
}

/** Run and throw on non-zero exit (like check=True). */
export async function runChecked(cmd: string[], o: RunOpts = {}): Promise<RunResult> {
  const r = await run(cmd, o);
  if (r.code !== 0) throw new Error(`${cmd.slice(0, 3).join(" ")} failed (${r.code}): ${(r.stderr || r.stdout).slice(0, 500)}`);
  return r;
}
