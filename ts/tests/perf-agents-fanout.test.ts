import { expect, test } from "bun:test";
import { CIHealthAgent } from "../src/agents/ci_health/agent.ts";
import { PRSLAAgent } from "../src/agents/pr_sla/agent.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";

const telegram: any = { sendMessage: async () => true };
const base = (gh: any) => ({ githubClient: gh, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram, targetOwner: "me" });
/** Records peak in-flight calls: overlapping round-trips show up as peak > 1, exactly and without timing thresholds. */
function probe() {
  let inflight = 0, peak = 0;
  return { call: async <T>(v: T): Promise<T> => { peak = Math.max(peak, ++inflight); await Bun.sleep(5); inflight--; return v; }, peak: () => peak };
}
const recent = new Date(Date.now() - 3600_000).toISOString();

test("ci_health inspects repos concurrently and reports failures in repo order", async () => {
  const p = probe(), names = ["me/a", "me/b", "me/c", "me/d"];
  const gh: any = {
    getUserRepos: async () => names.map((full_name) => ({ owner: { login: "me" }, full_name })),
    getRepo: (n: string) => p.call({ full_name: n, private: true }),
    getRateLimit: async () => ({ resources: { core: { remaining: 5000, limit: 5000, reset: 0 } } }),
    getWorkflowRuns: (n: string) => p.call(n === "me/c" ? [] : [{ name: n, conclusion: "failure", created_at: recent, html_url: "u", head_branch: "main" }]),
  };
  const r: any = await new CIHealthAgent(base(gh)).run();
  expect(p.peak()).toBeGreaterThanOrEqual(3);
  expect(r.failures.map((f: any) => f.repo)).toEqual(["me/a", "me/b", "me/d"]);
});

test("pr_sla resolves PRs concurrently, skips failed lookups and nudges in input order", async () => {
  const p = probe(), nudged: number[] = [];
  const stale = (n: number) => ({ number: n, title: "t", html_url: `u${n}`, updated_at: new Date(Date.now() - 30 * 3600_000).toISOString(), base: { repo: { full_name: "me/r" } } });
  const gh: any = {
    searchPrs: async () => [1, 2, 3, 4],
    getPrFromIssue: (i: number) => p.call(null).then(() => { if (i === 2) throw new Error("gone"); return stale(i); }),
    getIssueComments: async () => [],
    commentOnPr: async (pr: any) => { nudged.push(pr.number); return { html_url: `c${pr.number}` }; },
  };
  const r: any = await new PRSLAAgent(base(gh)).run();
  expect(p.peak()).toBeGreaterThanOrEqual(3);
  expect(nudged).toEqual([1, 3, 4]);
  expect(r.count).toBe(3);
});
