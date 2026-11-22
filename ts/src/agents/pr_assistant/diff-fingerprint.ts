/**
 * Fingerprint of what a PR changes, independent of its base: only added/removed lines and file names count, so a clean
 * "update branch" merge keeps the fingerprint and the earlier approval still applies; any change to the PR's own lines does not.
 */
import { createHash } from "node:crypto";

type F = { filename: string; status?: string; patch?: string; sha?: string };
export function fingerprintFiles(files: F[]): string {
  const h = createHash("sha256");
  for (const f of [...files].sort((a, b) => a.filename.localeCompare(b.filename))) {
    h.update(`\0${f.filename}\0${f.status ?? ""}\0`);
    if (f.patch === undefined) { h.update(`blob:${f.sha ?? ""}`); continue; } // binary/huge: GitHub sends no patch
    for (const l of f.patch.split(/\r?\n/)) if ((l.startsWith("+") || l.startsWith("-")) && !l.startsWith("+++") && !l.startsWith("---")) h.update(l + "\n");
  }
  return h.digest("hex").slice(0, 16);
}
export async function prFingerprint(gh: { getFiles(repo: string, n: number): Promise<F[]> }, pr: Record<string, any>): Promise<string | null> {
  try { return fingerprintFiles(await gh.getFiles(pr.base.repo.full_name, pr.number)); } catch { return null; }
}
