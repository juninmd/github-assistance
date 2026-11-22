/**
 * Structured LLM evaluation of human PR comments before an autonomous merge. Evaluator failure/unavailability never approves
 * (returns `wait`); an explicit rejection returns `blocked` without the caller closing the PR.
 */
import { isBotGenerated, isCommand, isOwnerHuman } from "./owner-commands.ts";

type R = Record<string, any>;
const DECISION_RE = /\b(MERGE|REJECT)\b/gi;
/** "não mergeia", "nao faça merge", "don't merge", "do not merge", "segura", "aguarde", "wip". */
export const OWNER_OBJECTION_RE = /\b(n[ãa]o\s+(mergei?[ae]r?|fa[çc]a\s+(o\s+)?merge|mescl\w*)|don'?t\s+merge|do\s+not\s+merge|segur[ae]|aguard[ae]|espera|wip)\b/i;
const REVIEWER_ASSOCIATIONS = new Set(["OWNER", "MEMBER", "COLLABORATOR"]);
export type CommentDecision = { decision: "merge" | "wait" | "blocked"; reason: string };

/** (decision, reason); decision is null unless the answer has exactly one valid keyword. */
export function parseStructuredResponse(text?: string | null): [string | null, string] {
  if (typeof text !== "string" || !text.trim()) return [null, "invalid_response: empty"];
  const m = text.match(DECISION_RE) ?? [];
  if (m.length !== 1) return [null, `invalid_response: expected one MERGE/REJECT (got ${m.length})`];
  return [m[0].toUpperCase(), text.trim()];
}

export async function evaluateCommentsWithLlm(ai: { generate(p: string): Promise<string> } | null, comments: R[], isTrusted: (login: string) => boolean, owner = ""): Promise<CommentDecision> {
  // Outsider text reaches the LLM verbatim and could inject a MERGE verdict; only trusted-association humans count.
  // The owner's own objection is a deterministic veto, newest owner comment wins (no model needed, no outage can drop it).
  const mine = owner ? comments.filter((c) => c.user && isOwnerHuman(c, owner) && !isCommand(String(c.body))) : [];
  const newest = mine[mine.length - 1];
  if (newest && OWNER_OBJECTION_RE.test(String(newest.body))) return { decision: "blocked", reason: `owner_objection: ${String(newest.body).slice(0, 120)}` };
  let human = comments.filter((c) => c.user && c.body && !isTrusted(c.user.login) && REVIEWER_ASSOCIATIONS.has(c.author_association) && !isBotGenerated(String(c.body)));
  human = human.slice(-10); // window after filtering so outsider floods can't push reviewer objections out
  if (!human.length) return { decision: "merge", reason: "no_human_review" };
  if (!ai) return { decision: "wait", reason: "evaluator_unavailable" };
  const text = human.map((c) => `@${c.user.login}: ${c.body.slice(0, 300)}`).join("\n");
  let response: string;
  try { response = await ai.generate(`Analyze PR comments:\n${text}\nReply with MERGE or REJECT. If REJECT, provide a short reason.`); }
  catch (e: any) { return { decision: "wait", reason: `evaluator_unavailable: ${e?.message ?? e}` }; }
  const [decision, reason] = parseStructuredResponse(response);
  if (decision === null) return { decision: "wait", reason };
  return decision === "REJECT" ? { decision: "blocked", reason: `llm_rejected: ${reason}` } : { decision: "merge", reason };
}
