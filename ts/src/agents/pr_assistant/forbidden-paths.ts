/** Paths an automated fix must never commit: build artifacts, vendored deps and env files. */
const ENV_TEMPLATES = new Set([".env.example", ".env.sample", ".env.template", ".env.dist"]);

export function isForbiddenPath(path: string): boolean {
  const parts = path.replace(/\\/g, "/").split("/");
  const base = parts[parts.length - 1] ?? "";
  if (parts.some((p) => p === "node_modules" || p === "__pycache__")) return true;
  if (/\.py[co]$/.test(base)) return true;
  return (base === ".env" || base.startsWith(".env.")) && !ENV_TEMPLATES.has(base);
}

export const forbiddenPaths = (paths: Iterable<string>): string[] => [...paths].filter(isForbiddenPath);
