/**
 * Conflict handling shared by the PR Assistant (inline, same cycle) and the Conflict Resolver agent: dependabot PRs get
 * `@dependabot rebase`, others are resolved under the per-PR lease; a failure is labelled for a human and the label is
 * cleared as soon as the PR is mergeable again.
 */
import type { GithubClient, PR } from "../../github/client.ts";
import { sendManualNotice } from "./conflict-notifications.ts";
import { isDependabot, requestDependabotRebase } from "./dependency-lane.ts";
import { withPrLock } from "./pr-lock.ts";

export const MANUAL_CONFLICT_LABEL = "needs-manual-conflict-resolution";
type Tg = { sendMessage(t: string, m?: string): Promise<boolean> };
type Log = (m: string, level?: string) => void;
export type Resolver = (pr: PR) => Promise<[boolean, string]>;
export type ConflictOutcome = { kind: "rebase_requested" | "rebase_pending" | "resolved" | "manual" | "busy" | "labelled"; msg: string };

export const hasLabel = (pr: PR, name: string) => (pr.labels ?? []).some((l: any) => (typeof l === "string" ? l : l.name) === name);

/** A PR that is mergeable again no longer needs a human for conflicts: drop the stale label so future conflicts are handled. */
export async function clearManualConflictLabel(gh: GithubClient, pr: PR, log: Log): Promise<void> {
  if (pr.mergeable !== true || !hasLabel(pr, MANUAL_CONFLICT_LABEL)) return;
  try { await gh.removeLabel(pr, MANUAL_CONFLICT_LABEL); log(`PR #${pr.number}: conflicts gone, removed '${MANUAL_CONFLICT_LABEL}'`); }
  catch (e) { log(`Could not remove '${MANUAL_CONFLICT_LABEL}' on PR #${pr.number}: ${e}`, "WARNING"); }
}
export async function markManualConflict(gh: GithubClient, tg: Tg, pr: PR, error: string, log: Log): Promise<void> {
  const author = pr.user?.login ?? "contributor";
  try {
    await gh.commentOnPr(pr, `**Nao foi possivel resolver os conflitos de merge**\n\nOla @${author}, tentei resolver os conflitos automaticamente sem sucesso.\n\n**Motivo:** ${error}\n\nMantive o PR aberto e marquei para resolucao manual.`);
  } catch (e) { log(`Failed to comment on PR #${pr.number}: ${e}`, "WARNING"); }
  const [ok, msg] = (await gh.addLabelToPr(pr, MANUAL_CONFLICT_LABEL)) ?? [true, ""];
  if (ok) log(`Marked PR #${pr.number} in ${pr.base.repo.full_name} for manual resolution`); else log(`Failed to label PR #${pr.number}: ${msg}`, "WARNING");
  await sendManualNotice(tg as any, pr, error);
}
/** Decide and act on a conflicted PR. The caller reports/notifies `resolved`. */
export async function handleConflict(gh: GithubClient, tg: Tg, pr: PR, comments: any[], resolve: Resolver, log: Log): Promise<ConflictOutcome> {
  if (isDependabot(pr.user?.login)) {
    const asked = await requestDependabotRebase(gh, pr, comments);
    return { kind: asked ? "rebase_requested" : "rebase_pending", msg: "@dependabot rebase" };
  }
  if (hasLabel(pr, MANUAL_CONFLICT_LABEL)) return { kind: "labelled", msg: "already flagged for manual resolution" };
  const r = await withPrLock(gh, pr, () => resolve(pr));
  if (r === null) return { kind: "busy", msg: "another agent holds the PR lease" };
  const [ok, msg] = r;
  if (ok) return { kind: "resolved", msg };
  await markManualConflict(gh, tg, pr, msg, log);
  return { kind: "manual", msg };
}
