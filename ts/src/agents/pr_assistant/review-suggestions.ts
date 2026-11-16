/**
 * GitHub "Apply suggestion" blocks for inline review comments. A suggestion replaces exactly the commented line, so it is
 * only offered when that line is the one the finding quoted; anything else would apply the fix to the wrong code.
 */
import { enabled } from "./review-flags.ts";
import type { Finding } from "./review-verdict.ts";

const HUNK = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/;
const MAX_LINES = 20;
export const suggestionsEnabled = () => enabled("REVIEW_SUGGESTIONS_ENABLED", true);
const squash = (s: string) => s.replace(/\s+/g, " ").trim();

/** New-side line → raw text (indentation intact) for the added and context lines of one file patch. */
export function rawLines(patch: string): Map<number, string> {
  const out = new Map<number, string>(); let cur = 0;
  for (const raw of (patch || "").split(/\r?\n/)) {
    const m = HUNK.exec(raw);
    if (m) { cur = parseInt(m[1]!, 10); continue; }
    if (!cur || raw.startsWith("\\") || raw.startsWith("-")) continue;
    out.set(cur++, raw.slice(1));
  }
  return out;
}
export type Source = Map<string, Map<number, string>>;
export const sourceFromFiles = (files: any[]): Source => new Map(files.map((f) => [f.filename, rawLines(f.patch ?? "")]));

/** Replacement code as the model wrote it, without a wrapping fence or trailing blank lines. */
function replacement(f: Finding): string {
  let s = String(f.suggestion ?? "").replace(/\r\n/g, "\n");
  const fence = /^\s*```[\w+-]*\n([\s\S]*?)\n?```\s*$/.exec(s);
  if (fence) s = fence[1]!;
  return s.replace(/\s+$/, "");
}
/**
 * The ```suggestion block for a finding, or "" when applying it could not be trusted: no quote, a multi-line quote
 * (the block would replace only one of the lines), a quote that is not the commented line, or a no-op/oversized fix.
 */
export function suggestionBlock(f: Finding, original: string | undefined): string {
  const quote = squash(String(f.evidence ?? "").replace(/^\s*[+-](?![+-])/, ""));
  if (!suggestionsEnabled() || original === undefined || !quote || /\n/.test(String(f.evidence ?? "").trim())) return "";
  const line = squash(original);
  if (!line || !(line.includes(quote) || quote.includes(line))) return "";
  let code = replacement(f);
  if (!code.trim() || squash(code) === line || code.split("\n").length > MAX_LINES || /^(<{7}|>{7}|={7}|\|{7})( |$)/m.test(code)) return "";
  // Models often drop the indentation; a suggestion is applied verbatim, so restore the commented line's.
  const indent = /^[ \t]*/.exec(original)![0];
  if (indent && !/^[ \t]/.test(code)) code = code.split("\n").map((l) => (l ? indent + l : l)).join("\n");
  const ticks = "`".repeat(Math.max(3, ...[...code.matchAll(/`+/g)].map((m) => m[0].length + 1)));
  return `${ticks}suggestion\n${code}\n${ticks}`;
}
