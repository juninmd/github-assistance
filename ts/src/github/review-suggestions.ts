/** Apply review suggestions from trusted bot reviewers to a PR branch. */
import type { GithubClient, PR } from "./client.ts";
import { GithubError } from "./client.ts";

const SUGGESTION_RE = /```suggestion[^\r\n]*\r?\n([\s\S]*?)\r?\n```/g;

export const normalizeLogin = (l?: string | null) => { let n = (l ?? "").trim().toLowerCase(); if (n.endsWith("[bot]")) n = n.slice(0, -5); return n; };

export function suggestionIndices(line: number, startLine?: number | null): [number, number] {
  if (Number.isInteger(startLine) && (startLine as number) > 0) return [Math.min(startLine!, line) - 1, Math.max(startLine!, line)];
  return [line - 1, line];
}

type Sugg = { start_idx: number; end_idx: number; suggestion: string; author: string };

export function parseSuggestions(comment: any): Sugg[] {
  const line = comment.line;
  if (!Number.isInteger(line) || line <= 0) return [];
  const [start_idx, end_idx] = suggestionIndices(line, comment.start_line);
  return [...(comment.body ?? "").matchAll(SUGGESTION_RE)].map((m) => ({ start_idx, end_idx, suggestion: m[1], author: comment.user?.login }));
}

export function collectSuggestions(comments: any[], bots: Set<string>): Map<string, Sugg[]> {
  const out = new Map<string, Sugg[]>();
  for (const c of comments) {
    if (!bots.has(normalizeLogin(c.user?.login))) continue;
    const list = parseSuggestions(c);
    if (list.length) out.set(c.path, [...(out.get(c.path) ?? []), ...list]);
  }
  return out;
}

export function applySuggestions(content: string, suggestions: Sugg[]): { text: string; authors: string[] } {
  let lines = content.split(/\r?\n/);
  if (lines[lines.length - 1] === "") lines.pop();
  const authors = new Set<string>();
  for (const s of [...suggestions].sort((a, b) => b.start_idx - a.start_idx)) {
    lines = [...lines.slice(0, s.start_idx), ...s.suggestion.split("\n"), ...lines.slice(s.end_idx)];
    authors.add(s.author);
  }
  return { text: lines.join("\n"), authors: [...authors] };
}

export async function acceptReviewSuggestions(gh: GithubClient, pr: PR, botUsernames: string[]): Promise<[boolean, string, number]> {
  try {
    const bots = new Set(botUsernames.filter((u) => typeof u === "string" && u.trim()).map(normalizeLogin));
    let comments: any[];
    try { comments = await gh.getReviewComments(pr.base.repo.full_name, pr.number); }
    catch (e) { if (e instanceof GithubError) return [false, `Failed to fetch review comments: ${e.status} ${JSON.stringify(e.data)}`, 0]; throw e; }
    const bySuggestion = collectSuggestions(comments, bots);
    if (!bySuggestion.size) return [true, "No suggestions found to apply", 0];
    const repo = pr.head.repo.full_name;
    let applied = 0;
    for (const [path, suggestions] of bySuggestion) {
      try {
        const f = await gh.getContents(repo, path, pr.head.ref);
        if (!f) continue;
        const { text, authors } = applySuggestions(f.content, suggestions);
        const co = authors.map((a) => `Co-authored-by: ${a} <${a}@users.noreply.github.com>`).join("\n");
        await gh.updateFile(repo, path, `Apply suggestion from ${authors.join(", ")}\n\n${co}\n`, text, f.sha, pr.head.ref);
        applied += suggestions.length;
      } catch (e: any) { console.log(`Error applying suggestion(s) to ${path}: ${e?.message ?? e}`); }
    }
    return applied > 0 ? [true, `Applied ${applied} suggestion(s)`, applied] : [true, "No suggestions found to apply", 0];
  } catch (e: any) { return [false, `Error processing review suggestions: ${e?.message ?? e}`, 0]; }
}
