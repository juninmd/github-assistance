/**
 * Evidence grounding: a finding only survives when the code it quotes really exists in the PR (or in the cloned repo).
 * The line number is taken from where the quote was found, never from the model. Deterministic, no model call.
 */
import type { Finding } from "./review-verdict.ts";

export type Drop = { finding: Finding; reason: string };
export type Grounded = { findings: Finding[]; dropped: Drop[] };
export type ReadFile = (path: string) => string | null;

const HUNK = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/;
const PSEUDO = /^\(.*\)$/;
const MIN_NEEDLE = 8;
const norm = (s: string) => s.replace(/\s+/g, " ").trim();
export const isPseudoFile = (file: string) => !file || PSEUDO.test(file);
export const cleanPath = (file: string) => file.trim().replace(/^[`'"]+|[`'"]+$/g, "").replace(/\\/g, "/").replace(/^\.\//, "");
/** Models often echo the `a/`/`b/` diff prefix; only strip it when that is what makes the path match. */
const resolvePath = (file: string, sections: Record<string, string>) => {
  const p = cleanPath(file), bare = p.replace(/^[ab]\//, "");
  return sections[p] === undefined && sections[bare] !== undefined ? bare : p;
};

export type Sides = { added: Map<number, string>; context: Map<number, string>; removed: string[] };
/** New-side line → text for added and context lines, plus removed texts. */
export function sideLines(section: string): Sides {
  const sides: Sides = { added: new Map(), context: new Map(), removed: [] };
  let cur = 0;
  for (const raw of (section || "").split(/\r?\n/)) {
    const m = HUNK.exec(raw);
    if (m) { cur = parseInt(m[1]!, 10); continue; }
    if (!cur || raw.startsWith("\\")) continue;
    if (raw.startsWith("-")) { sides.removed.push(norm(raw.slice(1))); continue; }
    (raw.startsWith("+") ? sides.added : sides.context).set(cur++, norm(raw.slice(1)));
  }
  return sides;
}
/** Longest meaningful line of the quoted evidence, without diff markers or a pasted line-number prefix. */
export function needle(evidence?: string | null): string {
  const lines = String(evidence ?? "").split(/\r?\n/).map((l) => norm(l.replace(/^\s*\d+\s*[:|]\s?/, "").replace(/^[+-](?![+-])/, "").replace(/^`+|`+$/g, "")));
  const best = lines.sort((a, b) => b.length - a.length)[0] ?? "";
  return (best.match(/[\p{L}\p{N}]/gu)?.length ?? 0) >= 3 ? best : "";
}
/** A short quote must be the whole line (it would match anywhere otherwise); a longer one may be part of it. */
const hit = (text: string, n: string) => (n.length < MIN_NEEDLE ? text === n : text.includes(n) || (text.length >= MIN_NEEDLE * 2 && n.includes(text)));
const findIn = (lines: Map<number, string>, n: string, near: number): number => {
  let best = 0;
  for (const [no, text] of lines) if (hit(text, n) && (!best || Math.abs(no - near) < Math.abs(best - near))) best = no;
  return best;
};
/** New-side line where the evidence sits: >0 found, 0 found only in removed code, -1 not in this diff. */
export function locate(section: string, n: string, near = 0): number {
  const s = sideLines(section);
  return findIn(s.added, n, near) || findIn(s.context, n, near) || (s.removed.some((t) => hit(t, n)) ? 0 : -1);
}
function locateInFile(content: string | null, n: string): number {
  if (!content) return -1;
  const i = content.split(/\r?\n/).findIndex((l) => hit(norm(l), n));
  return i === -1 ? -1 : i + 1;
}
/** Keep only findings whose file and quoted code are real; an `error` with no quote is capped at `warn`. */
export function groundFindings(findings: Finding[], sections: Record<string, string>, readFile: ReadFile = () => null): Grounded {
  const out: Grounded = { findings: [], dropped: [] };
  for (const raw of findings) {
    if (!raw.issue.trim()) continue;
    if (isPseudoFile(raw.file)) { out.findings.push(raw); continue; }
    const f = { ...raw, file: resolvePath(raw.file, sections) };
    const section = sections[f.file], n = needle(f.evidence);
    if (section === undefined) {
      const line = n ? locateInFile(readFile(f.file), n) : -1;
      if (line === -1) out.dropped.push({ finding: f, reason: "arquivo fora do PR" }); else out.findings.push({ ...f, line });
      continue;
    }
    if (!n) { out.findings.push(f.severity === "error" || f.severity === "critical" ? { ...f, severity: "warn" } : f); continue; }
    let line = locate(section, n, f.line);
    if (line === -1) line = locateInFile(readFile(f.file), n);
    if (line === -1) out.dropped.push({ finding: f, reason: "evidência não existe no código" }); else out.findings.push({ ...f, line });
  }
  return out;
}
