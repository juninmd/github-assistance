/** Helpers for the Secret Remover agent. */
import { Glob } from "bun";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

type Log = (m: string, level?: string) => void;

export function findLatestResults(log: Log, resultsGlob: string): Record<string, any> | null {
  const bases: string[] = [];
  if (process.env.RESULTS_DIR) bases.push(process.env.RESULTS_DIR);
  bases.push(process.cwd(), resolve(import.meta.dir, "..", "..", ".."));
  const files = new Set<string>();
  for (const base of bases) {
    try {
      log(`Searching for results in: ${join(base, resultsGlob)}`);
      for (const f of new Glob(resultsGlob).scanSync({ cwd: base, absolute: true })) files.add(resolve(f));
    } catch (e: any) { log(`Error searching for results in ${base}: ${e?.message ?? e}`, "WARNING"); }
  }
  for (const c of [...files].sort().reverse()) {
    try {
      const d = JSON.parse(readFileSync(c, "utf8"));
      if (!d || typeof d !== "object" || Array.isArray(d)) { log(`Ignoring invalid scanner result (not a dict): ${c}`, "WARNING"); continue; }
      if (!("repositories_with_findings" in d)) { log(`Ignoring invalid scanner result (missing key): ${c}`, "WARNING"); continue; }
      return d;
    } catch (e: any) { log(e instanceof SyntaxError ? `Ignoring malformed JSON in ${c}: ${e.message}` : `Error reading scanner result ${c}: ${e?.message ?? e}`, "WARNING"); }
  }
  return null;
}

/** Mask likely secret material before sending file context to the AI. */
export function redactContextLine(line: string): string {
  let r = line.replace(/(["'])([^"']{6,})(["'])/g, (_m, a, _b, c) => `${a}<redacted>${c}`);
  r = r.replace(/([=:]\s*)([^,\s#]+)/g, "$1<redacted>");
  r = r.replace(/\b[A-Za-z0-9_\-/+=]{12,}\b/g, "<redacted>");
  return r.slice(0, 240);
}

const readLines = (cloneDir: string, finding: Record<string, any>): string[] | null => {
  const f = finding.file ?? "";
  if (!f) return null;
  const p = join(cloneDir, f);
  if (!existsSync(p)) return null;
  return readFileSync(p, "utf8").split(/\r?\n/);
};

export function buildRedactedContext(cloneDir: string, finding: Record<string, any>): string {
  if (!(finding.file ?? "")) return "Context unavailable: missing file path.";
  if (!existsSync(join(cloneDir, finding.file))) return "Context unavailable: file not found in cloned repository.";
  let lines: string[];
  try { lines = readLines(cloneDir, finding)!; } catch (e: any) { return `Context unavailable: ${e?.message ?? e}`; }
  const idx = Math.max((parseInt(finding.line, 10) || 0) - 1, 0), start = Math.max(idx - 2, 0), end = Math.min(idx + 3, lines.length);
  const out: string[] = [];
  for (let i = start; i < end; i++) out.push(`${i === idx ? ">" : " "} ${i + 1}: ${redactContextLine(lines[i].trimEnd())}`);
  return out.join("\n").slice(0, 1000);
}

/** Raw (unredacted) original line, for Telegram reporting. */
export function getOriginalLine(cloneDir: string, finding: Record<string, any>): string {
  try {
    const lines = readLines(cloneDir, finding);
    if (!lines) return "";
    const idx = Math.max((parseInt(finding.line, 10) || 0) - 1, 0);
    return idx >= 0 && idx < lines.length ? lines[idx].trimEnd() : "";
  } catch { return ""; }
}

export const buildCommitUrl = (repo: string, sha: string) => `https://github.com/${repo}/commit/${sha}`;
export const buildFileLineUrl = (repo: string, sha: string, file: string, line: number) => `https://github.com/${repo}/blob/${sha}/${file}#L${line}`;
export const buildRepoUrl = (repo: string) => `https://github.com/${repo}`;
