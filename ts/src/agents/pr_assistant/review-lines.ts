/** Line validation and de-duplication of review findings (deterministic reflection). */
import type { GithubClient } from "../../github/client.ts";
import { sourceFromFiles, suggestionBlock, type Source } from "./review-suggestions.ts";
import type { Finding } from "./review-verdict.ts";

const HUNK = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/;
const FILE = /^\+\+\+ b\/(.+)$/;

export function parsePatch(patch: string): Set<number> {
  const lines = new Set<number>();
  let cur = 0;
  for (const raw of (patch || "").split(/\r?\n/)) {
    const m = HUNK.exec(raw);
    if (m) { cur = parseInt(m[1]!, 10); continue; }
    if (!cur || raw.startsWith("\\") || raw.startsWith("-")) continue;
    lines.add(cur++);
  }
  return lines;
}
export function parseDiff(diff: string): Map<string, Set<number>> {
  const result = new Map<string, Set<number>>();
  let path = ""; let chunk: string[] = [];
  const flush = () => { if (path) { const s = result.get(path) ?? new Set(); for (const n of parsePatch(chunk.join("\n"))) s.add(n); result.set(path, s); } };
  for (const raw of (diff || "").split(/\r?\n/)) {
    const m = FILE.exec(raw);
    if (raw.startsWith("diff --git ")) { flush(); path = ""; chunk = []; }
    else if (m) path = m[1]!;
    else chunk.push(raw);
  }
  flush();
  return result;
}
const key = (f: Finding) => `${f.file}\0${f.line}\0${f.issue.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim()}`;
export function validateFindings(findings: Iterable<Finding>, visible: Map<string, Set<number>>): Finding[] {
  const out: Finding[] = []; const seen = new Set<string>();
  for (let f of findings) {
    if (!f.issue.trim()) continue;
    if (f.line && !visible.get(f.file)?.has(f.line)) f = { ...f, line: 0 };
    const k = key(f);
    if (seen.has(k)) continue;
    seen.add(k); out.push(f);
  }
  return out;
}
const ICONS: Record<string, string> = { error: "🔴", warn: "🟠", warning: "🟠", nit: "🟡", info: "🔵" };
/** One inline comment per finding on a visible line; with `source`, a one-click "Apply suggestion" block when the fix is local to that line. */
export const inlineComments = (findings: Iterable<Finding>, visible: Map<string, Set<number>>, source?: Source) =>
  [...findings].filter((f) => f.line && visible.get(f.file)?.has(f.line)).map((f) => {
    const suggestion = source ? suggestionBlock(f, source.get(f.file)?.get(f.line)) : "";
    return { path: f.file, line: f.line, side: "RIGHT", body: `${ICONS[f.severity] ?? "🟡"} **${f.severity}** — ${f.issue}${suggestion ? `\n\n${suggestion}` : ""}` };
  });
/** Visible new-side lines per file from the PR's file patches. */
export async function visibleFromPr(gh: GithubClient, pr: any): Promise<Map<string, Set<number>>> {
  const files = await gh.getFiles(pr.base.repo.full_name, pr.number);
  return new Map(files.map((f: any) => [f.filename, parsePatch(f.patch ?? "")]));
}
/** Visible lines and their raw text from a single files call. */
export async function prLines(gh: GithubClient, pr: any): Promise<{ visible: Map<string, Set<number>>; source: Source }> {
  const files = await gh.getFiles(pr.base.repo.full_name, pr.number);
  return { visible: new Map(files.map((f: any) => [f.filename, parsePatch(f.patch ?? "")])), source: sourceFromFiles(files) };
}
