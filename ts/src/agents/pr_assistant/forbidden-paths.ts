import { closeSync, openSync, readSync } from "node:fs";
import { join } from "node:path";
import { isGenerated } from "./review-triage.ts";

/** Paths an automated fix must never commit: build artifacts, vendored deps and env files. */
const VENDOR_DIRS = new Set(["node_modules", "__pycache__", ".venv", "venv"]);
const ENV_TEMPLATES = new Set([".env.example", ".env.sample", ".env.template", ".env.dist"]);

export function isForbiddenPath(path: string): boolean {
  const parts = path.replace(/\\/g, "/").split("/");
  const base = parts[parts.length - 1] ?? "";
  if (parts.some((p) => VENDOR_DIRS.has(p))) return true;
  if (/\.py[co]$/.test(base)) return true;
  return (base === ".env" || base.startsWith(".env.")) && !ENV_TEMPLATES.has(base);
}

export const forbiddenPaths = (paths: Iterable<string>): string[] => [...paths].filter(isForbiddenPath);

const headOf = (dir: string, path: string): string => {
  let fd = -1;
  try { fd = openSync(join(dir, path), "r"); const buf = Buffer.alloc(2000); return buf.toString("utf8", 0, readSync(fd, buf, 0, 2000, 0)); }
  catch { return ""; } finally { if (fd !== -1) closeSync(fd); }
};
/** Changed files that are generated (path pattern or header marker): an automated fix must regenerate them, never hand-edit. */
export const generatedPaths = (dir: string, paths: Iterable<string>): string[] => [...paths].filter((p) => isGenerated(p, headOf(dir, p)));
