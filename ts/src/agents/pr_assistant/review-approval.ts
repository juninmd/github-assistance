/** SHA-pinned review approval read back from the bot's own review comment: the merge gate's single source of truth. */
import { OPENCODE_REVIEW_MARKER } from "./opencode-reviewer.ts";

export type ApprovalState = "approved" | "changes" | "missing";
const norm = (s: string) => s.toLowerCase().replace("[bot]", "");
// Model-written text precedes the verdict/footer lines, so the LAST match is always the one the bot rendered.
const last = (re: RegExp, s: string): string | null => { let r: string | null = null; for (const m of s.matchAll(new RegExp(re.source, "g"))) r = m[1]!; return r; };

/** Newest review comment by a trusted reviewer for exactly `headSha` decides; none for this SHA means "missing" (new push = re-review). */
export function approvalState(comments: any[], headSha: string, reviewers: string[]): ApprovalState {
  const who = new Set(reviewers.map(norm)), head = headSha.toLowerCase();
  for (const c of [...comments].reverse()) {
    const body: string = c.body ?? "";
    if (!body.includes(OPENCODE_REVIEW_MARKER) || !who.has(norm(c.user?.login ?? ""))) continue;
    const sha = last(/SHA `([0-9a-f]{7,40})`/, body)?.toLowerCase();
    if (!sha || !head.startsWith(sha)) continue;
    return last(/\*\*Veredito:\*\* `([A-Z_]+)`/, body) === "APPROVE" ? "approved" : "changes";
  }
  return "missing";
}
