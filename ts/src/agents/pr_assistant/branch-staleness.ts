/** How far a PR head lags its base: a failing check on a stale branch often validates a stale merge commit, fixable only by updating from base. */
import type { GithubClient, PR } from "../../github/client.ts";
export async function commitsBehind(gh: GithubClient, pr: PR): Promise<number> {
  try {
    const cmp = await gh.compare(pr.base.repo.full_name, pr.base.ref, pr.head.ref);
    return Number.isInteger(cmp.behind_by) ? Math.max(0, cmp.behind_by) : 0;
  } catch { return 0; } // best-effort
}
