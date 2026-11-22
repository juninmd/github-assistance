import { describe, expect, test } from "bun:test";
import { PRSLAAgent } from "../src/agents/pr_sla/agent.ts";
import { BranchCleanerAgent } from "../src/agents/branch_cleaner/agent.ts";
import { CIHealthAgent } from "../src/agents/ci_health/agent.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { GithubError } from "../src/github/client.ts";

const sent: string[] = [];
const telegram: any = { sendMessage: async (m: string) => { sent.push(m); return true; } };
const base = (gh: any) => ({ githubClient: gh, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram, targetOwner: "me" });
const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();

describe("pr_sla", () => {
  const pr = (n: number, h: number) => ({ number: n, title: "t", html_url: `u${n}`, updated_at: hoursAgo(h), base: { repo: { full_name: "me/r" } } });
  test("nudges stale PRs once and dedupes", async () => {
    const comments: string[] = [];
    const gh: any = {
      searchPrs: async () => [1, 2], getPrFromIssue: async (i: number) => pr(i, i === 1 ? 30 : 2),
      getIssueComments: async () => comments.map((body) => ({ body })),
      commentOnPr: async (_p: any, body: string) => { comments.push(body); return { html_url: "c" }; },
    };
    const a = new PRSLAAgent(base(gh));
    const r = await a.run();
    expect(r.count).toBe(1); expect(r.nudged).toEqual(["c"]);
    expect(comments[0]).toContain("SLA Alert");
    expect((await a.run()).nudged).toEqual([]);
  });
});

describe("branch_cleaner", () => {
  test("deletes only merged, non-default, non-protected", async () => {
    const del: string[] = [];
    const gh: any = {
      getUserRepos: async () => [{ owner: { login: "me" }, full_name: "me/r" }], getRepo: async () => ({ default_branch: "main" }),
      getBranches: async () => [{ name: "main" }, { name: "prot", protected: true }, { name: "merged" }, { name: "wip" }],
      compare: async (_r: string, _b: string, h: string) => ({ ahead_by: h === "merged" ? 0 : 3 }),
      deleteBranch: async (_r: string, b: string) => { del.push(b); },
    };
    const r = await new BranchCleanerAgent(base(gh)).run();
    expect(del).toEqual(["merged"]); expect(r.deleted_branches).toEqual(["me/r#merged"]);
  });
  test("records failed deletions", async () => {
    const gh: any = {
      getUserRepos: async () => [{ owner: { login: "me" }, full_name: "me/r" }], getRepo: async () => ({ default_branch: "main" }),
      getBranches: async () => [{ name: "b" }], compare: async () => ({ ahead_by: 0 }),
      deleteBranch: async () => { throw new GithubError(500, "boom"); },
    };
    expect((await new BranchCleanerAgent(base(gh)).run()).failed_branches).toEqual(["me/r#b"]);
  });
});

describe("ci_health", () => {
  test("collects failures and remediates public repos only", async () => {
    const tasks: string[] = [];
    const gh: any = {
      getUserRepos: async () => [{ owner: { login: "me" }, full_name: "me/pub" }, { owner: { login: "me" }, full_name: "me/priv" }],
      getRepo: async (n: string) => ({ full_name: n, private: n.endsWith("priv") }),
      getRateLimit: async () => ({ resources: { core: { remaining: 5000, limit: 5000, reset: 0 } } }),
      getWorkflowRuns: async () => [
        { name: "ci", conclusion: "failure", created_at: hoursAgo(1), html_url: "u", head_branch: "main" },
        { name: "ok", conclusion: "success", created_at: hoursAgo(1), html_url: "u" },
        { name: "old", conclusion: "failure", created_at: hoursAgo(48), html_url: "u" }],
    };
    const a = new CIHealthAgent(base(gh));
    (a as any).createOpencodeTask = async (repo: string) => { tasks.push(repo); return { status: "task_created", task_id: "1", task_url: "tu" }; };
    const r = await a.run();
    expect(r.count).toBe(2); expect(tasks).toEqual(["me/pub"]); expect(r.fix_actions).toHaveLength(1);
  });
});
