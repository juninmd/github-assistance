import { describe, expect, test } from "bun:test";
import { IntelligenceStandardizerAgent } from "../src/agents/intelligence_standardizer/agent.ts";
import { ProductManagerAgent } from "../src/agents/product_manager/agent.ts";
import { SeniorDeveloperAgent } from "../src/agents/senior_developer/agent.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";

const telegram: any = { sendMessage: async () => true };
const base = (gh: any) => ({ githubClient: gh, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram, targetOwner: "me" });
const repoOf = (n: string) => ({ owner: { login: "me" }, full_name: n, name: n.split("/")[1], default_branch: "main", updated_at: "2026-01-01T00:00:00Z" });

describe("intelligence_standardizer", () => {
  test("skips standardized, runs opencode for missing", async () => {
    const files: Record<string, string[]> = { "me/ok": ["AGENTS.md", ".agents", ".github/workflows/standard.yml", "CONTRIBUTING.md", "LICENSE"], "me/bad": [] };
    const gh: any = { getUserRepos: async () => [repoOf("me/ok"), repoOf("me/bad")], pathExists: async (r: string, p: string) => files[r].includes(p) };
    const created: string[] = [];
    const a = new IntelligenceStandardizerAgent(base(gh));
    a.loadTaskInstructions = () => "instr"; a.runOpencodeOnRepo = async (r: string) => { created.push(r); return { pr_url: "u" }; };
    const r = await a.run();
    expect(r.skipped).toEqual([{ repository: "me/ok", reason: "already_standardized" }]);
    expect(created).toEqual(["me/bad"]); expect(r.processed[0]).toMatchObject({ pr_url: "u", missing_agents_md: true });
  });
});

describe("product_manager", () => {
  const mk = (commits: any[], issues: any[], aiResp = "{}") => {
    const gh: any = { getUserRepos: async () => [repoOf("me/r")], getRepo: async () => ({ ...repoOf("me/r"), description: "d", language: "TS" }), getPathCommits: async () => commits, getOpenIssues: async () => issues };
    const a = new ProductManagerAgent({ ...base(gh), enforceRepositoryAllowlist: false, aiClient: { generate: async () => aiResp } } as any);
    (a as any).enforceRepositoryAllowlist = false; a.loadTaskInstructions = () => "i"; a.runOpencodeOnRepo = async () => ({ pr_url: "u" });
    return a;
  };
  test("skips fresh roadmap", async () => {
    const r = await mk([{ commit: { author: { date: new Date().toISOString() } } }], []).analyzeAndCreateRoadmap("me/r");
    expect(r).toMatchObject({ skipped: true, reason: "roadmap_up_to_date" });
  });
  test("builds analysis from issues + AI JSON", async () => {
    const issues = [{ number: 1, title: "x", labels: [{ name: "bug" }] }];
    const r = await mk([], issues, 'noise {"ai_summary":"sum","priorities":[{"category":"A","count":1,"urgency":"high"}]}').analyzeAndCreateRoadmap("me/r");
    expect(r).toMatchObject({ pr_url: "u", analysis_summary: "sum", priority_count: 1 });
  });
  test("falls back to label counts without AI JSON", async () => {
    const r = await mk([], [{ number: 1, title: "x", labels: [{ name: "Feature" }] }]).analyzeAndCreateRoadmap("me/r");
    expect(r.priority_count).toBe(3); expect(r.analysis_summary).toBe("Repository has 1 open issues");
  });
});

describe("senior_developer", () => {
  test("daily limit selection", () => {
    const a = new SeniorDeveloperAgent({ ...base({}), aiClient: {} as any } as any);
    process.env.SENIOR_DEVELOPER_DAILY_REPO_LIMIT = "2"; expect(a.selectDaily(["a", "b", "c"])).toEqual(["a", "b"]);
    process.env.SENIOR_DEVELOPER_DAILY_REPO_LIMIT = "0"; expect(a.selectDaily(["a"])).toEqual([]);
    delete process.env.SENIOR_DEVELOPER_DAILY_REPO_LIMIT;
  });
  test("analyzers detect gitignore/ci/debt findings and run creates tasks", async () => {
    process.env.SENIOR_DEVELOPER_REPO_DELAY_MS = "0";
    const gh: any = {
      getUserRepos: async () => [repoOf("me/r")], getRepo: async () => repoOf("me/r"), get: async () => ({ resources: { core: { remaining: 5000, limit: 5000, reset: 0 } } }),
      getContents: async () => null, listContents: async () => null, pathExists: async () => false, getOpenIssues: async () => [],
      getTree: async () => [{ path: "src/big.ts", size: 50000 }, ...Array.from({ length: 6 }, (_, i) => ({ path: `utils${i}.js`, size: 1 }))],
    };
    const a = new SeniorDeveloperAgent({ ...base(gh), aiClient: { generate: async () => "x" } } as any);
    (a as any).enforceRepositoryAllowlist = false;
    const tasks: string[] = []; a.loadTaskInstructions = () => "i"; a.createOpencodeTask = async (_r: string, _i: string, t: string) => { tasks.push(t); return { pr_url: "http://pr" }; };
    expect((await a.analyzer.analyzeSecurity("me/r")).issues).toEqual(["Missing .gitignore file"]);
    expect((await a.analyzer.analyzeCicd("me/r")).improvements).toContain("Set up GitHub Actions for CI/CD");
    const td = await a.analyzer.analyzeTechDebt("me/r"); expect(td.details).toContain("Large file detected: `src/big.ts`"); expect(td.details).toContain("High number of utility files (6)");
    expect((await a.analyzer.analyzeModernization("me/r")).details).toContain("TypeScript migration");
    const r = await a.run();
    expect(r.failed).toEqual([]); expect(tasks).toContain("Security Hardening for me/r"); expect(tasks).toContain("Tech Debt Cleanup for me/r");
    expect(r.security_tasks[0].opencode.pr_url).toBe("http://pr");
  });
});
