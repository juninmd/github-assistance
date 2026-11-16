/** Split a big PR diff into packages of related files, one review each; per-repo rules via .review/rules.json. */
import { readFileSync } from "node:fs";
import { join, posix } from "node:path";
import { APPROVE, REQUEST_CHANGES, type ReviewVerdict } from "./review-verdict.ts";

export const RULES_FILE = ".review/rules.json";
const MAX_RULES_CHARS = 1500;

export function maxPackages(): number {
  const n = parseInt(process.env.REVIEW_MAX_PACKAGES || "", 10);
  return Number.isNaN(n) ? 4 : Math.max(1, n || 4);
}
export function splitByFile(diff: string): Record<string, string> {
  const sections: Record<string, string> = {};
  let cur = ""; let buf: string[] = [];
  for (const line of diff.split(/(?<=\n)/)) {
    if (line.startsWith("diff --git ")) {
      if (cur) sections[cur] = buf.join("");
      buf = [line];
      cur = line.includes(" b/") ? line.split(" b/").slice(1).join(" b/").trim() : "";
    } else buf.push(line);
  }
  if (cur) sections[cur] = buf.join("");
  return sections;
}
export function buildPackages(sections: Record<string, string>, budget: number): Record<string, string>[] {
  const groups = new Map<string, Record<string, string>>();
  for (const [path, text] of Object.entries(sections)) {
    const dir = posix.dirname(path);
    const g = groups.get(dir) ?? {}; g[path] = text.slice(0, budget); groups.set(dir, g);
  }
  const packages: Record<string, string>[] = [];
  let cur: Record<string, string> = {}; let size = 0;
  for (const files of groups.values()) for (const [path, text] of Object.entries(files)) {
    if (Object.keys(cur).length && size + text.length > budget) { packages.push(cur); cur = {}; size = 0; }
    cur[path] = text; size += text.length;
  }
  if (Object.keys(cur).length) packages.push(cur);
  return packages;
}
export type Rule = { path: string; rule: string };
export function loadRules(cloneDir: string): Rule[] {
  let data: any;
  try { data = JSON.parse(readFileSync(join(cloneDir, RULES_FILE), "utf8")); } catch { return []; }
  const rules = data && !Array.isArray(data) && typeof data === "object" ? data.rules ?? data : data;
  return Array.isArray(rules)
    ? rules.filter((r) => r && typeof r === "object" && r.path && r.rule).map((r) => ({ path: String(r.path), rule: String(r.rule) })) : [];
}
/** Glob → RegExp (fnmatch: * ? [seq], `*` crosses `/`). */
export function fnmatch(name: string, pat: string): boolean {
  let re = "";
  for (let i = 0; i < pat.length; i++) {
    const c = pat[i]!;
    if (c === "*") re += ".*"; else if (c === "?") re += ".";
    else if (c === "[") { const j = pat.indexOf("]", i + 2); if (j === -1) re += "\\["; else { re += "[" + pat.slice(i + 1, j).replace(/^!/, "^").replace(/\\/g, "\\\\") + "]"; i = j; } }
    else re += c.replace(/[.+^${}()|\\]/g, "\\$&");
  }
  return new RegExp(`^${re}$`, "s").test(name);
}
export function rulesText(rules: Rule[], files: string[]): string {
  const hits = rules.filter((r) => files.some((f) => fnmatch(f, r.path))).map((r) => `- \`${r.path}\`: ${r.rule}`);
  return hits.length ? ("Regras específicas deste repositório:\n" + hits.join("\n")).slice(0, MAX_RULES_CHARS) + "\n" : "";
}
const uniq = <T>(a: T[]) => [...new Set(a)];
export function mergeVerdicts(vs: ReviewVerdict[]): ReviewVerdict {
  const blocked = vs.some((v) => v.verdict === REQUEST_CHANGES);
  return { ...vs[0]!, verdict: blocked ? REQUEST_CHANGES : APPROVE, summary: uniq(vs.map((v) => v.summary).filter(Boolean)).join(" | "),
    findings: vs.flatMap((v) => v.findings), skills_used: uniq(vs.flatMap((v) => v.skills_used)) };
}
