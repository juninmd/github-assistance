import { closeSync, openSync, readSync, rmSync } from "node:fs";
import { join } from "node:path";
import { run } from "../../utils/proc.ts";
import { isGenerated } from "./review-triage.ts";

/** Paths an automated fix must never commit: build artifacts, vendored deps, env files and agent instruction files. */
const VENDOR_DIRS = new Set(["node_modules", "__pycache__", ".venv", "venv"]);
const ENV_TEMPLATES = new Set([".env.example", ".env.sample", ".env.template", ".env.dist"]);
// Agent instructions are owner policy: a fix once overwrote a public AGENTS.md with private instructions (radar-ofertas#23).
const AGENT_INSTRUCTIONS = new Set(["agents.md", "agent.md", "claude.md", "gemini.md", "copilot-instructions.md", ".cursorrules", ".windsurfrules", ".clinerules"]);
const AGENT_INSTRUCTION_DIRS = [".cursor/rules/", ".github/instructions/", ".clinerules/"];

export function isForbiddenPath(path: string): boolean {
  const parts = path.replace(/\\/g, "/").split("/");
  const base = parts[parts.length - 1] ?? "";
  if (parts.some((p) => VENDOR_DIRS.has(p))) return true;
  if (/\.py[co]$/.test(base)) return true;
  if (AGENT_INSTRUCTIONS.has(base.toLowerCase())) return true;
  const normalized = `/${parts.join("/").toLowerCase()}`;
  if (AGENT_INSTRUCTION_DIRS.some((d) => normalized.includes(`/${d}`))) return true;
  return (base === ".env" || base.startsWith(".env.")) && !ENV_TEMPLATES.has(base);
}

export const forbiddenPaths = (paths: Iterable<string>): string[] => [...paths].filter(isForbiddenPath);

/** Delete untracked (incl. ignored) deps/artifacts/env files a fix run created (npm install, pytest, .env), so staging and the secret scan see only intended changes; tracked ones stay and are still rejected. */
export async function pruneUntrackedForbidden(dir: string): Promise<string[]> {
  const dropped: string[] = [];
  // First pass collapses whole untracked dirs (cheap for node_modules); second catches files inside new source dirs.
  for (const extra of [["--directory"], []]) {
    const r = await run(["git", "ls-files", "--others", ...extra, "-z"], { cwd: dir, timeoutMs: 60_000 });
    const drop = r.code === 0 ? forbiddenPaths(r.stdout.split("\0").filter(Boolean)) : [];
    for (const p of drop) rmSync(join(dir, p), { recursive: true, force: true });
    dropped.push(...drop);
  }
  return dropped;
}

const headOf = (dir: string, path: string): string => {
  let fd = -1;
  try { fd = openSync(join(dir, path), "r"); const buf = Buffer.alloc(2000); return buf.toString("utf8", 0, readSync(fd, buf, 0, 2000, 0)); }
  catch { return ""; } finally { if (fd !== -1) closeSync(fd); }
};
/** Changed files that are generated (path pattern or header marker): an automated fix must regenerate them, never hand-edit. */
export const generatedPaths = (dir: string, paths: Iterable<string>): string[] => [...paths].filter((p) => isGenerated(p, headOf(dir, p)));
