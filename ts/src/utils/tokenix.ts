/** Optional tokenix integration for opencode runs (fail-open). Only calls the external binary; never modifies it. */
import { createHash } from "node:crypto";
import { existsSync, readdirSync, rmSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { realpathSync } from "node:fs";

export const CONFIG_ENV = "OPENCODE_CONFIG_CONTENT";
const STALE_SECONDS = 7200;
const TOOL_PREFIX = "tokenix_";

export const enabled = () => ["1", "true", "yes", "on"].includes((process.env.TOKENIX_ENABLED ?? "true").trim().toLowerCase());
export const binary = (): string | null => Bun.which(process.env.TOKENIX_BIN?.trim() || "tokenix");
const indexTimeoutMs = () => Math.max(5, parseInt(process.env.TOKENIX_INDEX_TIMEOUT_SECONDS ?? "", 10) || 120) * 1000;
const home = () => process.env.TOKENIX_HOME || join(homedir(), ".tokenix");

const versions = new Map<string, string>();
export function version(cmd: string): string {
  if (versions.has(cmd)) return versions.get(cmd)!;
  let v = "";
  try { const o = Bun.spawnSync([cmd, "--version"], { timeout: 15_000 }).stdout.toString().trim().split(/\s+/); v = o[o.length - 1] ?? ""; } catch { /* unreadable */ }
  versions.set(cmd, v);
  return v;
}

/** Register the tokenix MCP server for opencode via env; true when active. */
export function configureEnviron(env: Record<string, string | undefined> = process.env): boolean {
  const cmd = enabled() ? binary() : null;
  if (!cmd) return false;
  let config: any;
  try { config = JSON.parse(env[CONFIG_ENV] || "{}"); if (typeof config.mcp !== "undefined" && (typeof config.mcp !== "object" || config.mcp === null)) return false; } catch { return false; }
  config.mcp ??= {};
  config.mcp.tokenix ??= { type: "local", command: [cmd, "mcp"], enabled: true };
  env[CONFIG_ENV] = JSON.stringify(config);
  return true;
}

export function isActive(): boolean {
  try { return !!binary() && enabled() && "tokenix" in (JSON.parse(process.env[CONFIG_ENV] || "{}").mcp ?? {}); } catch { return false; }
}
export const harnessSuffix = (active: boolean) => { const c = binary(); return active && c ? ` + tokenix ${version(c)}`.trimEnd() : ""; };
export const calls = (tools: string[]) => tools.filter((t) => t.startsWith(TOOL_PREFIX)).length;

function projectFiles(cloneDir: string): string[] {
  const ident = createHash("sha256").update(realpathSync(resolve(cloneDir))).digest("hex").slice(0, 16);
  try { return readdirSync(home()).filter((f) => f.startsWith(ident + ".")).map((f) => join(home(), f)); } catch { return []; }
}
export function sweepStale(now = Date.now() / 1000): void {
  const h = home();
  if (!existsSync(h)) return;
  for (const f of readdirSync(h)) {
    if (!/^[0-9a-f]{16}\./.test(f)) continue;
    try { if (statSync(join(h, f)).mtimeMs / 1000 < now - STALE_SECONDS) rmSync(join(h, f)); } catch { /* ignore */ }
  }
}

/** Build the clone's index around `fn`; passes true when tokenix is usable for the run. */
export async function session<T>(cloneDir: string, fn: (ready: boolean) => Promise<T>, log: (m: string, level?: string) => void = () => {}): Promise<T> {
  const cmd = binary();
  if (!(cmd && isActive())) return fn(false);
  try {
    sweepStale();
    let ready = false;
    try {
      const r = Bun.spawnSync([cmd, "index", "."], { cwd: cloneDir, timeout: indexTimeoutMs() });
      ready = r.exitCode === 0;
      if (!ready) log(`tokenix off for this run (index rc=${r.exitCode})`, "WARNING");
    } catch (e: any) { log(`tokenix off for this run (index failed: ${e?.message ?? e})`, "WARNING"); }
    return await fn(ready);
  } finally {
    for (const p of projectFiles(cloneDir)) { try { rmSync(p); } catch { /* ignore */ } }
  }
}
