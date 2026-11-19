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
