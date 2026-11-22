/**
 * Per-PR lease shared by the agents that push to a PR branch (review autofix, pipeline fix, conflict resolution): the
 * `bot/busy` label. A lease older than the TTL (PR untouched for that long) is considered abandoned and taken over.
 */
import type { GithubClient, PR } from "../../github/client.ts";

export const BUSY_LABEL = "bot/busy";
const TTL_MS = 30 * 60_000;
const hasBusy = (pr: PR) => (pr.labels ?? []).some((l: any) => (typeof l === "string" ? l : l.name) === BUSY_LABEL);

export async function acquirePrLock(gh: GithubClient, pr: PR, now = Date.now()): Promise<boolean> {
  let fresh = pr;
  try { fresh = await gh.getPull(pr.base.repo.full_name, pr.number); } catch { /* use the snapshot */ }
  if (hasBusy(fresh) && now - Date.parse(fresh.updated_at ?? "") < TTL_MS) return false;
  try { const [ok] = await gh.addLabelToPr(pr, BUSY_LABEL); return ok !== false; } catch { return true; } // labels are best-effort; never block work on them
}
export async function releasePrLock(gh: GithubClient, pr: PR): Promise<void> {
  try { await gh.removeLabel(pr, BUSY_LABEL); } catch { /* best-effort */ }
}
/** Run `fn` holding the PR lease; null when another agent holds it. */
export async function withPrLock<T>(gh: GithubClient, pr: PR, fn: () => Promise<T>): Promise<T | null> {
  if (!(await acquirePrLock(gh, pr))) return null;
  try { return await fn(); } finally { await releasePrLock(gh, pr); }
}
