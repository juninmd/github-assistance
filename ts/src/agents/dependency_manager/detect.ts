/** Detect a repository's dependency ecosystems from its tracked files (pure, no GitHub access). */
const SPECS: [string, string[], string[], string, string][] = [
  ["node", ["package.json"], ["package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb"], "npm audit --json (ou pnpm audit / yarn audit)", "npm outdated (ou pnpm outdated / yarn outdated)"],
  ["python", ["pyproject.toml", "requirements.txt", "setup.py", "Pipfile"], ["uv.lock", "poetry.lock", "Pipfile.lock"], "pip-audit / osv-scanner", "uv pip list --outdated (ou pip list --outdated)"],
  ["go", ["go.mod"], ["go.sum"], "govulncheck", "go list -u -m all"],
  ["rust", ["Cargo.toml"], ["Cargo.lock"], "cargo audit", "cargo outdated"],
  ["php", ["composer.json"], ["composer.lock"], "composer audit", "composer outdated"],
];
export type Ecosystem = { name: string; manifest: string; lockfile: string | null; auditHint: string; outdatedHint: string };
export const ecosystemSummary = (e: Ecosystem) => `${e.name} (${e.manifest}, ${e.lockfile ?? "sem lockfile"})`;
export const rootFilenames = (files: Iterable<string>): Set<string> => new Set([...files].filter((f) => f && !f.replace(/^\/+|\/+$/g, "").includes("/")).map((f) => f.toLowerCase()));
export function detectEcosystems(files: Iterable<string>): Ecosystem[] {
  const present = rootFilenames(files), found: Ecosystem[] = [];
  for (const [name, manifests, locks, auditHint, outdatedHint] of SPECS) {
    const manifest = manifests.find((m) => present.has(m.toLowerCase()));
    if (!manifest) continue;
    found.push({ name, manifest, lockfile: locks.find((l) => present.has(l.toLowerCase())) ?? null, auditHint, outdatedHint });
  }
  return found;
}
