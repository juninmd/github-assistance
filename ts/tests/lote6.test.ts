import { describe, expect, test } from "bun:test";
import { InterfaceDeveloperAgent } from "../src/agents/interface_developer/agent.ts";
import { ReadmeCuratorAgent } from "../src/agents/readme_curator/agent.ts";
import { scoreReadme } from "../src/agents/readme_curator/scoring.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";

const telegram: any = { sendMessage: async () => true };
const base = (gh: any) => ({ githubClient: gh, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram, targetOwner: "me" });

describe("readme scoring", () => {
  test("empty and strong readmes", () => {
    expect(scoreReadme("")).toEqual({ score: 0, missing: ["title", "description", "installation", "usage"] });
    const good = `# Proj\n\n${"A long description about the project. ".repeat(5)}\n\n[![b](https://img.shields.io/x.svg)](u)\n\n## Installation\nsetup\n## Usage\nrun it\n## Configuration\n.env\n## Contributing\n## License\n\n\`\`\`mermaid\ngraph TD\n\`\`\`\n`;
    const s = scoreReadme(good); expect(s.score).toBeGreaterThanOrEqual(80); expect(s.missing).toEqual([]);
  });
  test("weak readme lists missing", () => {
    const s = scoreReadme("# Title\nshort"); expect(s.score).toBe(5); expect(s.missing).toContain("installation");
  });
});

describe("readme_curator", () => {
  const repo = (n: string, o: any = {}) => ({ owner: { login: "me" }, full_name: n, name: n.split("/")[1], default_branch: "main", ...o });
  test("missing → task; fresh+good → skipped; archived → skipped; oldest first", async () => {
    const good = `# P\n\n${"Description sentence here. ".repeat(6)}\n[![b](https://img.shields.io/x.svg)](u)\n## Install\n## Usage\n## Config\n## Contributing\n## License\n![x](y.png)\n`;
    const repos: Record<string, any> = { "me/miss": repo("me/miss"), "me/good": repo("me/good"), "me/arch": repo("me/arch", { archived: true }) };
    const gh: any = {
      getUserRepos: async () => Object.values(repos), getRepo: async (n: string) => repos[n], get: async () => ({ resources: { core: { remaining: 5000, limit: 5000, reset: 0 } } }),
      getReadme: async (n: string) => (n === "me/miss" ? null : { path: "README.md", content: good }),
      getPathCommits: async () => [{ commit: { committer: { date: new Date().toISOString() } } }],
    };
    const a = new ReadmeCuratorAgent(base(gh)); const order: string[] = [];
    a.createOpencodeTask = async (r: string) => { order.push(r); return { task_url: "u", status: "task_created" }; };
    const r = await a.run();
    expect(order).toEqual(["me/miss"]); expect(r.processed[0]).toMatchObject({ reason: "missing", pr_url: "u" });
    expect(r.skipped.map((s: any) => s.reason).sort()).toEqual(["already_good", "archived_or_fork"]);
  });
  test("stale readme is processed", async () => {
    const good = `# P\n\n${"Description sentence here. ".repeat(6)}\n[![b](https://img.shields.io/x.svg)](u)\n## Install\n## Usage\n## Config\n## Contributing\n## License\n![x](y.png)\n`;
    const gh: any = { getUserRepos: async () => [repo("me/old")], getRepo: async () => repo("me/old"), get: async () => ({ resources: { core: { remaining: 5000, limit: 5000, reset: 0 } } }),
      getReadme: async () => ({ path: "README.md", content: good }), getPathCommits: async () => [{ commit: { committer: { date: "2020-01-01T00:00:00Z" } } }] };
    const a = new ReadmeCuratorAgent(base(gh)); a.createOpencodeTask = async () => ({ task_url: "u", status: "ok" });
    expect((await a.run()).processed[0].reason).toContain("stale");
  });
});

describe("interface_developer", () => {
  test("creates issue + opencode PR for frontend repo with UI issues", async () => {
    const created: any[] = [];
    const gh: any = {
      getUserRepos: async () => [], getRepo: async () => ({ language: "TypeScript", full_name: "me/r", default_branch: "main" }),
      getOpenIssues: async () => [{ title: "Fix layout", body: "", number: 1 }, { title: "other", body: "none" }], pathExists: async () => false,
      get: async () => ({}), post: async () => ({}), createIssue: async (_r: string, o: any) => { created.push(o); return { number: 9, html_url: "iu" }; },
    };
    const a = new InterfaceDeveloperAgent({ ...base(gh), aiClient: { generate: async () => "## Objective\nx" } } as any);
    (a as any).getAllowedRepositories = async () => ["me/r"]; (a as any).runOpencodeOnRepo = async () => ({ pr_url: "pu" });
    const r = await a.run() as any;
    expect(created[0].labels).toEqual(["roadmap"]); expect(created[0].body).toContain("## Objective");
    expect(r.ui_issues_created[0]).toMatchObject({ issue_url: "iu", opencode_pr_url: "pu" });
    expect(r.ui_issues_created[0].improvements).toEqual(["Resolve UI issue: Fix layout", "Create DESIGN.md with design system documentation"]);
  });
  test("non-frontend language → no work", async () => {
    const gh: any = { getRepo: async () => ({ language: "Python" }), getOpenIssues: async () => [], pathExists: async () => false };
    const a = new InterfaceDeveloperAgent(base(gh) as any);
    expect((await a.analyzeUiNeeds("me/r")).has_ui_work).toBe(false);
  });
});
