import { describe, expect, test } from "bun:test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { CodeReviewerAgent } from "../src/agents/code_reviewer/agent.ts";
import { DependencyManagerAgent } from "../src/agents/dependency_manager/agent.ts";
import { detectEcosystems } from "../src/agents/dependency_manager/detect.ts";
import { SecretRemoverAgent } from "../src/agents/secret_remover/agent.ts";
import { buildAllowlistToml, buildSecurityBranch } from "../src/agents/secret_remover/git-utils.ts";
import { buildRedactedContext, findLatestResults, redactContextLine } from "../src/agents/secret_remover/utils.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { tmp } from "./helpers.ts";

const telegram: any = { sendMessage: async () => true };
const base = (gh: any) => ({ githubClient: gh, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram, targetOwner: "me" });

describe("code_reviewer", () => {
  const pr = { number: 7, title: "t", base: { repo: { full_name: "me/r" } } };
  const mk = (response: string, extra: any = {}) => {
    const posted: any[] = [];
    const gh: any = {
      getUserRepos: async () => [{ owner: { login: "me" }, full_name: "me/r" }], getPulls: async () => [pr],
      getAuthenticatedLogin: async () => "bot", getIssueComments: async () => extra.comments ?? [],
      getFiles: async () => [{ filename: "a.ts", status: "modified", additions: 1, deletions: 0, patch: "+x" }],
      createReview: async (_p: any, o: any) => { if (extra.reviewFails) throw new Error("x"); posted.push(["review", o]); return {}; },
      commentOnPr: async (_p: any, b: string) => { posted.push(["comment", b]); return {}; },
    };
    const a = new CodeReviewerAgent({ ...base(gh), aiClient: { generate: async () => response } });
    return { a, posted };
  };
  test("posts inline review for issues with line", async () => {
    const { a, posted } = mk('{"issues":[{"severity":"high","file":"a.ts","line":3,"description":"bug","suggestion":"fix"}],"summary":"s"}');
    const r = await a.run();
    expect(r.reviews_performed).toHaveLength(1);
    expect(posted[0][0]).toBe("review"); expect(posted[0][1].comments[0]).toMatchObject({ path: "a.ts", line: 3 });
    expect(posted[0][1].body).toContain("<!-- code-review -->");
  });
  test("falls back to comment, skips already reviewed", async () => {
    const { a, posted } = mk('{"issues":[],"summary":"ok"}');
    await a.run(); expect(posted[0][0]).toBe("comment"); expect(posted[0][1]).toContain("No issues found");
    const s = mk("{}", { comments: [{ body: "<!-- code-review -->", user: { login: "bot" } }] });
    expect((await s.a.run()).reviews_performed).toHaveLength(0);
  });
});

describe("dependency_manager", () => {
  test("detects ecosystems from root files only", () => {
    const e = detectEcosystems(["package.json", "bun.lockb", "src/go.mod", "Cargo.toml"]);
    expect(e.map((x) => x.name)).toEqual(["node", "rust"]); expect(e[0].lockfile).toBe("bun.lockb"); expect(e[1].lockfile).toBeNull();
  });
  test("dry run and skip", async () => {
    process.env.DEPENDENCY_DRY_RUN = "1";
    const gh: any = {
      getUserRepos: async () => [{ owner: { login: "me" }, full_name: "me/a" }, { owner: { login: "me" }, full_name: "me/b" }],
      getRateLimit: async () => ({}), get: async () => ({ resources: { core: { remaining: 5000, limit: 5000, reset: 0 } } }),
      getRepo: async (n: string) => ({ full_name: n, name: n.split("/")[1], default_branch: "main" }),
      getTreePaths: async (n: string) => (n.endsWith("a") ? ["pyproject.toml"] : ["README.md"]),
    };
    const a = new DependencyManagerAgent({ ...base(gh), enforceRepositoryAllowlist: false });
    (a as any).enforceRepositoryAllowlist = false;
    const r = await a.run(); delete process.env.DEPENDENCY_DRY_RUN;
    expect(r.processed[0]).toMatchObject({ repository: "me/a", status: "dry_run", ecosystems: ["python"] });
    expect(r.skipped[0]).toMatchObject({ repository: "me/b", reason: "no_dependencies" });
  });
});

describe("secret_remover", () => {
  test("redacts context line and builds window", () => {
    const l = redactContextLine('key = "supersecretvalue" # x');
    expect(l).not.toContain("supersecretvalue");
    const d = tmp(); writeFileSync(join(d, "f.env"), 'a=1\nTOKEN="abcdefghijkl"\nz=2\n');
    const c = buildRedactedContext(d, { file: "f.env", line: 2 });
    expect(c).toContain("> 2:"); expect(c).not.toContain("abcdefghijkl");
    expect(buildRedactedContext(d, { file: "nope" })).toContain("not found");
  });
  test("finds latest valid scanner result", () => {
    const d = tmp(); mkdirSync(join(d, "results"));
    writeFileSync(join(d, "results", "security-scanner_20260101.json"), JSON.stringify({ repositories_with_findings: [{ repository: "old" }] }));
    writeFileSync(join(d, "results", "security-scanner_20260102.json"), "{bad");
    process.env.RESULTS_DIR = d;
    const r = findLatestResults(() => {}, "results/security-scanner_*.json"); delete process.env.RESULTS_DIR;
    expect(r?.repositories_with_findings[0].repository).toBe("old");
  });
  test("allowlist toml + branch names", () => {
    const t = buildAllowlistToml("[x]\n", [{ rule_id: "r1", file: "a/b.txt" }]);
    expect(t).toBe('[x]\n\n[[allowlist]]\ndescription = "False positive: r1 in a/b.txt"\nrules = ["r1"]\npaths = ["a/b.txt"]\n');
    expect(buildSecurityBranch("Me/My_Repo", new Date("2026-01-02T03:04:05Z"))).toBe("agent/security-hardening-for-me-my-repo-20260102030405");
  });
  test("run without results reports error; AI IGNORE default is processor-level", async () => {
    const d = tmp(); process.env.RESULTS_DIR = d;
    const a = new SecretRemoverAgent({ ...base({}), aiClient: {} as any });
    const cwd = process.cwd(); process.chdir(d);
    const r = await a.run(); process.chdir(cwd); delete process.env.RESULTS_DIR;
    expect(r.error).toContain("No security scanner results");
  });
});
