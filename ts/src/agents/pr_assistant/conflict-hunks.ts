/**
 * Merge conflicts are resolved one block at a time. The model only ever writes the lines that replace a block, so code
 * outside the conflict stays byte-identical by construction, and blocks that need no judgement never reach a model.
 */
const START = "<<<<<<<", BASE = "|||||||", SEP = "=======", END = ">>>>>>>";
export const DEFAULT_CONTEXT_LINES = 12;
/** A model answer much bigger than both sides together is a rewritten file, not a merged block. */
const MAX_GROWTH = 3, GROWTH_SLACK = 400;

/** Keep line terminators like Python's splitlines(keepends=True). */
export const splitKeepEnds = (s: string): string[] => s.match(/[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+/g) ?? [];
const rstripNl = (s: string) => s.replace(/[\r\n]+$/, "");
const isMarker = (line: string, m: string) => line === m || line.startsWith(m + " ");
/** True when conflict markers (start, base or end) are still in the text. */
export const hasMarkers = (text: string) => /^(<{7}|>{7}|\|{7})( |$)/m.test(text);

/** Inclusive `[start, end]` line spans, or null on malformed markers. */
export function findHunks(lines: string[]): [number, number][] | null {
  const spans: [number, number][] = []; let start: number | null = null;
  for (let i = 0; i < lines.length; i++) {
    if (isMarker(lines[i]!, START)) { if (start !== null) return null; start = i; }
    else if (isMarker(lines[i]!, END)) { if (start === null) return null; spans.push([start, i]); start = null; }
  }
  return start !== null ? null : spans;
}
export type Hunk = { ours: string[]; base: string[] | null; theirs: string[] };
/** Split one conflict block (markers included) into its sides; `base` exists only with the diff3/zdiff3 conflict style. */
export function parseHunk(block: string[]): Hunk | null {
  const bare = block.map(rstripNl);
  const baseAt = bare.findIndex((l, i) => i > 0 && isMarker(l, BASE));
  const sepAt = bare.findIndex((l, i) => i > Math.max(0, baseAt) && l === SEP);
  if (sepAt === -1 || block.length < 3) return null;
  return { ours: block.slice(1, baseAt === -1 ? sepAt : baseAt), base: baseAt === -1 ? null : block.slice(baseAt + 1, sepAt), theirs: block.slice(sepAt + 1, -1) };
}
const squash = (ls: string[]) => ls.map((l) => l.replace(/\s+/g, " ").trim()).join("\n");
/** Blocks that need no judgement: both sides ended up equal, or only one side really changed the ancestor. */
export function trivialResolution(h: Hunk): string[] | null {
  const ours = squash(h.ours), theirs = squash(h.theirs);
  if (ours === theirs) return h.ours;
  if (h.base && squash(h.base) === ours) return h.theirs;
  if (h.base && squash(h.base) === theirs) return h.ours;
  return null;
}
/** Drop context the model echoed back around its answer (2+ whole lines, so real code is never eaten by accident). */
function trimEcho(answer: string[], pre: string[], post: string[]): string[] {
  const eq = (a: string[], b: string[]) => a.length === b.length && a.every((x, i) => rstripNl(x) === rstripNl(b[i]!));
  let out = answer;
  for (let k = Math.min(pre.length, out.length); k >= 2; k--) if (eq(out.slice(0, k), pre.slice(pre.length - k))) { out = out.slice(k); break; }
  for (let k = Math.min(post.length, out.length); k >= 2; k--) if (eq(out.slice(out.length - k), post.slice(0, k))) { out = out.slice(0, out.length - k); break; }
  return out;
}
export const CANNOT_RESOLVE = "CANNOT_RESOLVE";
/** Model text → replacement lines, or null when it is not a usable merge of this block. */
export function cleanAnswer(raw: string | null | undefined, hunk: Hunk, pre: string[], post: string[], eol: string): string[] | null {
  let text = (raw ?? "").replace(/\r\n/g, "\n");
  const fence = /^\s*```[\w+-]*\n([\s\S]*?)\n?```\s*$/.exec(text);
  if (fence) text = fence[1]!;
  if (!text.trim() || text.includes(CANNOT_RESOLVE) || hasMarkers(text) || /^={7}$/m.test(text)) return null;
  const sides = [...hunk.ours, ...hunk.theirs].join("").length;
  if (text.length > sides * MAX_GROWTH + GROWTH_SLACK) return null;
  const lines = trimEcho(splitKeepEnds(text.replace(/\n*$/, "\n")), pre, post);
  return lines.length ? lines.map((l) => rstripNl(l) + eol) : null;
}
export type HunkContext = { pre: string[]; block: string[]; post: string[]; hunk: Hunk };
export type Resolution = { text: string; auto: number; asked: number };
/**
 * Resolve every conflict block of `content`. `ask` is called only for blocks that need judgement and returns the raw
 * model answer; null from it (or an unusable answer) aborts the whole file, so a file is never half-resolved.
 */
export async function resolveHunks(content: string, ask: (c: HunkContext) => Promise<string | null>, contextLines = DEFAULT_CONTEXT_LINES): Promise<Resolution | null> {
  const lines = splitKeepEnds(content), spans = findHunks(lines.map(rstripNl));
  if (!spans || !spans.length) return null;
  const eol = content.includes("\r\n") ? "\r\n" : "\n";
  const out: string[] = []; let cursor = 0, auto = 0, asked = 0;
  for (let n = 0; n < spans.length; n++) {
    const [s, e] = spans[n]!, block = lines.slice(s, e + 1), hunk = parseHunk(block);
    if (!hunk) return null;
    let replacement = trivialResolution(hunk);
    if (replacement) auto++;
    else {
      const pre = lines.slice(Math.max(n ? spans[n - 1]![1] + 1 : 0, s - contextLines), s);
      const post = lines.slice(e + 1, Math.min(n + 1 < spans.length ? spans[n + 1]![0] : lines.length, e + 1 + contextLines));
      replacement = cleanAnswer(await ask({ pre, block, post, hunk }), hunk, pre, post, eol);
      if (!replacement) return null;
      asked++;
    }
    out.push(...lines.slice(cursor, s), ...replacement);
    cursor = e + 1;
  }
  out.push(...lines.slice(cursor));
  return { text: out.join(""), auto, asked };
}
