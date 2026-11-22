/** How an agent's pull requests are opened: builder PRs stay draft and carry `keep-draft`, so the bot never merges them. */
import type { GithubClient, PR } from "../../github/client.ts";

export const KEEP_DRAFT_LABEL = "keep-draft";
export type PrOptions = { draft: boolean; labels: string[] };
export const DEFAULT_PR_OPTIONS: PrOptions = { draft: false, labels: [] };
type Log = (m: string, level?: string) => void;

export const hasLabel = (pr: { labels?: any[] }, name: string) =>
  (pr.labels ?? []).some((l: any) => (typeof l === "string" ? l : l?.name ?? "").toLowerCase() === name.toLowerCase());

/** Create the PR as draft when asked; repos without draft support still get the label that blocks the bot's merge. */
export async function createAgentPull(gh: GithubClient, repo: string, p: { title: string; body: string; head: string; base: string }, o: PrOptions, log: Log): Promise<PR> {
  let pr: PR;
  try { pr = await gh.createPull(repo, o.draft ? { ...p, draft: true } : p); }
  catch (e: any) {
    if (!o.draft || !/draft/i.test(String(e?.message ?? e))) throw e;
    log(`Draft PRs unavailable in ${repo}; opening a regular PR guarded by '${o.labels.join(", ")}'`, "WARNING");
    pr = await gh.createPull(repo, p);
  }
  for (const label of o.labels) await gh.addLabelToPr(pr, label);
  return pr;
}
