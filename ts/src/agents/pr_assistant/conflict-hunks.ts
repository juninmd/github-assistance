/**
 * Resolve merge conflicts hunk by hunk instead of sending the whole file. Each conflict block is sent with a few lines of
 * context and spliced back only if the untouched context came back byte-identical, so a model rewriting unrelated code cannot
 * corrupt the file.
 */
const START = "<<<<<<<", SEP = "=======", END = ">>>>>>>";
export const DEFAULT_CONTEXT_LINES = 12, DEFAULT_THRESHOLD_CHARS = 6000;
export const hunkThreshold = () => { const n = parseInt(process.env.CONFLICT_HUNK_THRESHOLD || "", 10); return Number.isNaN(n) ? DEFAULT_THRESHOLD_CHARS : n; };

/** Keep line terminators like Python's splitlines(keepends=True). */
export const splitKeepEnds = (s: string): string[] => s.match(/[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+/g) ?? [];
const rstripNl = (s: string) => s.replace(/[\r\n]+$/, "");

/** Inclusive `[start, end]` line spans, or null on malformed markers. */
export function findHunks(lines: string[]): [number, number][] | null {
  const spans: [number, number][] = []; let start: number | null = null;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith(START)) { if (start !== null) return null; start = i; }
    else if (lines[i].startsWith(END)) { if (start === null) return null; spans.push([start, i]); start = null; }
  }
  return start !== null ? null : spans;
}
const same = (a: string[], b: string[]) => a.length === b.length && a.every((x, i) => x === b[i]);

/** Null if markers are malformed, a hunk fails, the model altered the context, or markers survive. */
export async function resolveByHunks(content: string, resolveSnippet: (snippet: string, hunk: string) => Promise<string>, contextLines = DEFAULT_CONTEXT_LINES): Promise<string | null> {
  const lines = splitKeepEnds(content), spans = findHunks(lines.map(rstripNl));
  if (!spans || !spans.length) return null;
  const out: string[] = []; let cursor = 0;
  for (let n = 0; n < spans.length; n++) {
    const [s, e] = spans[n], prevEnd = n ? spans[n - 1][1] + 1 : 0, nextStart = n + 1 < spans.length ? spans[n + 1][0] : lines.length;
    const preFrom = Math.max(prevEnd, s - contextLines, cursor), postTo = Math.min(nextStart, e + 1 + contextLines);
    const pre = lines.slice(preFrom, s), hunk = lines.slice(s, e + 1), post = lines.slice(e + 1, postTo);
    const resolved = await resolveSnippet([...pre, ...hunk, ...post].join(""), hunk.join(""));
    if (!resolved || [START, SEP + "\n", END].some((m) => resolved.includes(m))) return null;
    const nl = splitKeepEnds(resolved);
    if (nl.length < pre.length + post.length) return null;
    if (!same(nl.slice(0, pre.length), pre)) return null;
    const tail = post.length ? nl.slice(nl.length - post.length) : [];
    if (post.length && !same(tail.map(rstripNl), post.map(rstripNl))) return null;
    out.push(...lines.slice(cursor, preFrom), ...pre, ...nl.slice(pre.length, nl.length - post.length), ...post);
    cursor = postTo;
  }
  out.push(...lines.slice(cursor));
  return out.join("");
}
