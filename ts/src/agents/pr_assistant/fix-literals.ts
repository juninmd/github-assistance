/** Template literal → quoted string in an automated fix: `${x}` stops interpolating and ships as literal text. */
import { run } from "../../utils/proc.ts";

const JS_FILE = /\.(?:[cm]?[jt]sx?|vue|svelte|astro)$/i;
const TEMPLATE = /`(?:[^`\\]|\\.)*`/g;
const QUOTED = /(["'])(?:(?!\1)[^\\\n]|\\.)*?\$\{[^}]+\}(?:(?!\1)[^\\\n]|\\.)*?\1/g;
const exprs = (s: string) => [...s.matchAll(/\$\{([^}]+)\}/g)].map((m) => m[1]!.trim());

/** `file: "string"` for each added quoted string holding a `${expr}` that a removed template literal of the same file interpolated. */
export function brokenTemplates(diff: string): string[] {
  const out: string[] = [];
  for (const chunk of diff.split(/^--- .*$/m).slice(1)) {
    const file = /^\+\+\+ (?:b\/)?(.+)$/m.exec(chunk)?.[1]?.trim() ?? "";
    if (!JS_FILE.test(file)) continue;
    const lines = chunk.split(/\r?\n/);
    const was = new Set(lines.filter((l) => l.startsWith("-")).flatMap((l) => (l.match(TEMPLATE) ?? []).flatMap(exprs)));
    for (const l of lines) {
      if (!l.startsWith("+") || l.startsWith("+++")) continue;
      // Quotes inside a template (`"${a}"`) are fine: strip templates before looking for quoted interpolations.
      for (const q of l.slice(1).replace(TEMPLATE, "``").match(QUOTED) ?? []) if (exprs(q).some((e) => was.has(e))) out.push(`${file}: ${q}`);
    }
  }
  return out;
}
/** Reason to reject, or "" when no template literal was flattened; `cached` reads the index instead of the worktree. */
export async function literalReason(dir: string, cached = false): Promise<string> {
  const diff = (await run(["git", "diff", ...(cached ? ["--cached"] : []), "-U0"], { cwd: dir, timeoutMs: 30_000 })).stdout;
  const hits = brokenTemplates(diff);
  return hits.length ? `template literal turned into a plain string (\${…} would no longer interpolate): ${hits.slice(0, 5).join("; ")}` : "";
}
