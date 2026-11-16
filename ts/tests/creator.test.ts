import { describe, expect, test } from "bun:test";
import { ProjectCreatorAgent } from "../src/agents/project_creator/agent.ts";
import { nameProblem, parseJson, renderPrompt } from "../src/agents/project_creator/ideation/pipeline.ts";
import { IdeationPipeline } from "../src/agents/project_creator/ideation/pipeline.ts";
import { buildPortfolio } from "../src/agents/project_creator/ideation/portfolio.ts";
import { formatResearch, MarketResearcher } from "../src/agents/project_creator/ideation/research.ts";
import { domainSaturation, pickSeed, preferStacks } from "../src/agents/project_creator/ideation/seed.ts";
import { GithubError } from "../src/github/client.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { tmp } from "./helpers.ts";
import { join } from "node:path";

const seeded = (s = 42) => { let a = s; return { random: () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; } }; };

describe("ideation helpers", () => {
  test("parseJson tolerant of prose", () => { expect(parseJson('x {"a":1} y')).toEqual({ a: 1 }); expect(parseJson("no")).toBeNull(); expect(parseJson("{bad}")).toBeNull(); });
  test("nameProblem: generic, banned, similar", () => {
    expect(nameProblem("smart-app", [], false)).toBe("name is generic");
    expect(nameProblem("budget-tool", [], false)).toContain("banned");
    expect(nameProblem("budget-tool", [], true)).toBeNull();
    expect(nameProblem("log-tail-view", ["log-tail"], false)).toContain("too similar");
    expect(nameProblem("zebra-quartz", ["other-thing"], false)).toBeNull();
  });
  test("seed saturation lowers odds and is deterministic", () => {
    expect(domainSaturation(["my-cli git helper"])["developer tooling"]).toBe(1);
    const a = pickSeed([], seeded(1)), b = pickSeed([], seeded(1));
    expect(a).toEqual(b); expect(a.angles.length).toBeLessThanOrEqual(3);
  });
  test("preferStacks stable ordering", () => { expect(preferStacks(["Go", "Python + Typer", "Rust"], ["python"])).toEqual(["Python + Typer", "Go", "Rust"]); });
  test("portfolio splits autonomous repos", () => {
    const p = buildPortfolio([
      { name: "mine", language: "Go", description: "A hand built thing for me", owner: { login: "me" } },
      { name: "gen", description: "x | 🤖 Criado de forma autônoma pelo agente", owner: { login: "me" } },
      { name: "forked", fork: true, description: "long enough description" }, { name: "theirs", description: "long enough description here", owner: { login: "other" } }], "me");
    expect(p.exemplars).toEqual(["mine (Go): A hand built thing for me"]); expect(p.generated).toEqual(["gen"]); expect(p.languages).toEqual(["Go"]);
  });
  test("research format + web parsing + competitor filtering", async () => {
    const html = '<a class="result__a" href="http://x?a=1&amp;b=2">T&amp;C</a> junk <a class="result__snippet" href="#">snip <b>it</b></a>';
    const gh: any = {
      get: async () => ({ items: [{ full_name: "me/own", stargazers_count: 9 }, { full_name: "o/a", stargazers_count: 5, html_url: "u", language: "Go", description: "d" }] }),
      getReadme: async () => ({ content: "readme" }), listContents: async () => [{ path: "main.go" }],
    };
    const r = await new MarketResearcher(gh, () => {}, async () => ({ ok: true, status: 200, text: async () => html })).research(["q1", 5, " "], "me");
    expect(r.competitors.map((c) => c.name)).toEqual(["o/a"]); expect(r.web[0]).toEqual({ title: "T&C", url: "http://x?a=1&b=2", snippet: "snip it" });
    expect(formatResearch(r)).toContain("o/a (5★, Go)"); expect(formatResearch({})).toBe("none found");
  });
});

const goodSpec = (name = "zebra-quartz") => ({
  repository_name: name, title: "Zebra", idea_description: "x".repeat(90), tech_stack: "Go", problem: "p", target_user: "u", tagline: "tag",
  features: Array.from({ length: 4 }, (_, i) => ({ name: `f${i}`, description: "d", acceptance: "a" })),
  roadmap_features: Array.from({ length: 9 }, (_, i) => ({ title: `r${i}`, objective: `o${i}` })),
});

describe("pipeline", () => {
  const diverge = { candidates: [{ repository_name: "zebra-quartz" }, { repository_name: "smart-app" }] };
  const scores = { scores: [{ index: 0, novelty: 5, utility: 4, fit: 5, feasibility: 4, distinctiveness: 4 }] };
  const gen = (spec: any, sc: any = scores) => async (p: string) => JSON.stringify(p.includes("skeptical") ? sc : p.includes("principal engineer") ? spec : diverge);
  test("passes gate and renders prompt", async () => {
    const r = await new IdeationPipeline(gen(goodSpec()), () => {}, { rng: seeded(3), attempts: 1 }).run([], []);
    expect(r?.repository_name).toBe("zebra-quartz"); expect(r?.jules_prompt).toContain("### Features (all required for v1)"); expect(r?.jules_prompt).toContain("1. **f0**");
  });
  test("rejects low scores and bad specs", async () => {
    const low = { scores: [{ index: 0, novelty: 2, utility: 2, fit: 2, feasibility: 2, distinctiveness: 2 }] };
    expect(await new IdeationPipeline(gen(goodSpec(), low), () => {}, { rng: seeded(3), attempts: 2 }).run([], [])).toBeNull();
    expect(await new IdeationPipeline(gen({ ...goodSpec(), features: [] }), () => {}, { rng: seeded(3), attempts: 1 }).run([], [])).toBeNull();
  });
  test("renderPrompt includes competitors", () => {
    expect(renderPrompt({ ...goodSpec(), competitors: [{ name: "a/b", url: "u", strengths: "s", gaps: "g" }] })).toContain("### Competitive landscape\n- [a/b](u): strengths — s; gaps — g");
  });
});

describe("project_creator agent", () => {
  const mk = (over: any = {}) => {
    const dir = tmp(); const calls: string[] = []; const issues: any[] = [];
    const gh: any = { getUserRepos: async () => [], get: async () => ({ items: [] }), getReadme: async () => null, listContents: async () => [],
      createUserRepo: async (o: any) => { calls.push(`repo:${o.name}`); return { full_name: `me/${o.name}`, name: o.name, default_branch: over.defaultBranch ?? "master" }; },
      getRef: async () => ({ object: { sha: "s" } }), createRef: async () => { calls.push("ref"); }, editRepo: async () => { calls.push("edit"); },
      createIssue: async (_r: string, o: any) => { issues.push(o); return { number: issues.length, html_url: `iu${issues.length}` }; }, post: async () => ({}), delete: async () => ({}) };
    const jules: any = { getSourceName: (r: string) => `sources/github/${r}`, listSources: async () => over.noSource ? [] : [{ name: "sources/github/me/zebra-quartz" }], createPullRequestSession: async () => ({ id: "sess" }) };
    const diverge = { candidates: [{ repository_name: "zebra-quartz" }] }, scores = { scores: [{ index: 0, novelty: 5, utility: 5, fit: 5, feasibility: 5, distinctiveness: 5 }] };
    const ai: any = { generate: async (p: string) => JSON.stringify(p.includes("skeptical") ? scores : p.includes("principal engineer") ? goodSpec() : p.includes("search queries") ? { queries: [] } : diverge) };
    const a = new ProjectCreatorAgent({ githubClient: gh, julesClient: jules, allowlist: new RepositoryAllowlist(join(dir, "a.json")), telegram: { sendMessage: async () => true } as any, aiClient: ai, rng: seeded(5), targetOwner: "me" } as any);
    a.loadJulesInstructions = () => "instr"; (a as any).getRepositoryInfo = async () => ({ default_branch: "master" });
    return { a, calls, issues };
  };
  test("happy path creates repo, session, roadmap issues with both labels", async () => {
    const { a, calls, issues } = mk();
    const r = await a.run();
    expect(r).toMatchObject({ status: "session_created", repository: "me/zebra-quartz", session_id: "sess" }); expect(calls).toContain("repo:zebra-quartz");
    expect(issues).toHaveLength(9); expect(issues[0].labels).toEqual(["roadmap", "jules"]); expect(issues[0].body).toContain("## Objective\no0"); expect(r.roadmap_issues).toHaveLength(9);
  });
  test("non-master default branch gets a master ref", async () => {
    const { a, calls } = mk({ defaultBranch: "main" });
    await a.run(); expect(calls).toEqual(expect.arrayContaining(["ref", "edit"]));
  });
  test("fails when repo is not a Jules source", async () => {
    expect((await mk({ noSource: true }).a.run())).toMatchObject({ status: "failed", reason: "jules_source_missing" });
  });
  test("422 on branch creation falls back to edit", async () => {
    const { a } = mk(); (a.githubClient as any).createRef = async () => { throw new GithubError(422, "exists"); };
    expect(await a.ensureMasterBranch({ full_name: "me/x", default_branch: "main" })).toBe(true);
  });
  test("splitFeature handles string and object", () => {
    expect(ProjectCreatorAgent.splitFeature("  A ")).toEqual(["A", "A"]); expect(ProjectCreatorAgent.splitFeature({ title: "T" })).toEqual(["T", "T"]); expect(ProjectCreatorAgent.splitFeature({})).toEqual(["Roadmap item", "Roadmap item"]);
  });
});
