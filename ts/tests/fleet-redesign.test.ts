import { afterEach, expect, test } from "bun:test";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { AGENT_ALIASES, AGENT_CATALOG, AGENTS_BY_NAME, resolveAgentName } from "../src/agents/catalog.ts";
import { agentDir } from "../src/agents/core/utils.ts";
import { FlowWatchAgent } from "../src/agents/flow_watch/agent.ts";
import { SecretGuardAgent } from "../src/agents/secret_guard/agent.ts";
import { BuilderAgent } from "../src/agents/builder/agent.ts";
import { createAgentPull, KEEP_DRAFT_LABEL } from "../src/agents/core/pr-options.ts";
import { applyGate } from "../src/agents/pr_assistant/review-gate.ts";
import { APPROVE, mkVerdict } from "../src/agents/pr_assistant/review-verdict.ts";
import { contractLabel, ensureContract, resetContract } from "../src/agents/core/agent-contract.ts";
import { IntelligenceStandardizerAgent } from "../src/agents/intelligence_standardizer/agent.ts";
import { createAgent } from "../src/agents/registry.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { testSettings, tmp } from "./helpers.ts";

const telegram: any = { sendMessage: async () => true };
const base = (gh: any = {}, o: any = {}) => ({ githubClient: gh, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram, targetOwner: "me", ...o });
const fakeStages = (a: any, results: Record<string, any>, ran: string[] = []) => {
  a.createStage = async (st: any) => ({ run: async () => { ran.push(st.name); if (results[st.name] instanceof Error) throw results[st.name]; return results[st.name] ?? {}; } });
  return ran;
};
afterEach(() => { for (const k of ["PR_SLA_ENABLED", "AGENT_CONTRACT_REFRESH", "REPO_STANDARDS_MAX_PRS"]) delete process.env[k]; resetContract(); });

test("catalog: 8 scoped agents; every stage and former name resolves to real code", async () => {
  expect(AGENT_CATALOG).toHaveLength(8);
  for (const a of AGENT_CATALOG) {
    expect(existsSync(join(agentDir(a.name), "agent.ts"))).toBe(true);
    for (const st of a.stages) expect((await import(join(agentDir(st.dir), "agent.ts")))[st.className]).toBeDefined();
  }
  for (const [old, t] of Object.entries(AGENT_ALIASES)) {
    const spec = AGENTS_BY_NAME.get(t.agent)!;
    expect(spec).toBeDefined();
    if (t.stage) expect(spec.stages.map((s) => s.name)).toContain(t.stage);
    expect(AGENTS_BY_NAME.has(old)).toBe(false); // a former name never shadows a current agent
  }
  expect(resolveAgentName("pr-sla")).toEqual({ agent: "flow-watch", stage: "sla" });
  expect(resolveAgentName("code-reviewer")).toEqual({ agent: "pr-assistant" });
  expect(resolveAgentName("nope")).toBeNull();
});

test("registry: a former name builds the new agent restricted to its stage; AI stage still needs ENABLE_AI", async () => {
  const s = await testSettings();
  const a: any = await createAgent("ci-health", s);
  expect(a).toBeInstanceOf(FlowWatchAgent); expect(a.onlyStage).toBe("ci");
  await expect(createAgent("secret-remover", s)).rejects.toThrow("requires AI");
  const g: any = await createAgent("secret-guard", s); // scanning works without AI
  expect(g.onlyStage).toBeNull(); expect(g.opts.ai).toBeUndefined();
});

test("composite: stages run in order, toggles skip, a failed stage marks the run failed; a single stage passes through", async () => {
  const a: any = new FlowWatchAgent(base());
  const ran = fakeStages(a, { ci: { count: 2 }, sla: new Error("boom") });
  const r = await a.run();
  expect(ran).toEqual(["ci", "sla"]);
  expect(r.stages.ci).toEqual({ count: 2 }); expect(r.stages.sla.error).toBe("boom"); expect(r.error).toContain("sla");
  process.env.PR_SLA_ENABLED = "false";
  const b: any = new FlowWatchAgent(base()); const ran2 = fakeStages(b, {});
  const r2 = await b.run();
  expect(ran2).toEqual(["ci"]); expect(r2.skipped_stages).toEqual({ sla: "PR_SLA_ENABLED=false" }); expect(r2.error).toBeUndefined();
  const only: any = new FlowWatchAgent(base({}, { stage: "sla" })); fakeStages(only, { sla: { stale_pull_requests: [] } });
  expect(await only.run()).toEqual({ stale_pull_requests: [] }); // the former agent's exact result shape
  expect(() => new FlowWatchAgent(base({}, { stage: "ghost" }))).toThrow("unknown stage");
});

test("flow-watch only observes: no CI remediation tasks, no SLA nudge comments", async () => {
  const a: any = new FlowWatchAgent(base());
  expect((await a.createStage(a.stages[0])).remediate).toBe(false);
  const sla = await a.createStage(a.stages[1]);
  let commented = 0;
  sla.githubClient = { searchPrs: async () => [{}], getPrFromIssue: async () => ({ number: 1, title: "t", html_url: "u", updated_at: "2020-01-01T00:00:00Z", base: { repo: { full_name: "me/r" } } }),
    commentOnPr: async () => { commented++; return {}; }, getIssueComments: async () => [] };
  const r = await sla.run();
  expect(r.count).toBe(1); expect(commented).toBe(0); expect(r.nudged).toEqual([]);
});

test("secret-guard: the remover gets this run's scan, never runs after a failed scan nor without AI", async () => {
  const cwd = process.cwd(), d = tmp(); process.chdir(d);
  try {
    const scan = { repositories_with_findings: [{ repository: "me/r", findings: [] }] };
    const a: any = new SecretGuardAgent(base({}, { ai: { provider: "ollama", model: "m" } }));
    let got: any = null;
    a.createStage = async (st: any) => (st.name === "scan" ? { run: async () => scan } : { run: async () => { got = a.stageOptions(st).scanResults; return {}; } });
    await a.run();
    expect(got).toBe(scan);
    expect(readFileSync(join(d, "results", readdirSync(join(d, "results"))[0]!), "utf8")).toContain("me/r"); // kept for `run-agent secret-remover`
    const b: any = new SecretGuardAgent(base({}, { ai: { provider: "ollama", model: "m" } })); const ran = fakeStages(b, { scan: { error: "gitleaks missing" } });
    const r = await b.run();
    expect(ran).toEqual(["scan"]); expect(r.skipped_stages.remove).toBe("scan failed");
    const c: any = new SecretGuardAgent(base()); const ran3 = fakeStages(c, { scan: {} });
    expect((await c.run()).skipped_stages.remove).toBe("ENABLE_AI=false"); expect(ran3).toEqual(["scan"]);
  } finally { process.chdir(cwd); }
});

test("builder stages open draft PRs labelled keep-draft", async () => {
  const a: any = new BuilderAgent(base({}, { ai: { provider: "ollama", model: "m" }, aiClient: { generate: async () => "" } }));
  for (const st of a.stages) expect((await a.createStage(st)).prOptions).toEqual({ draft: true, labels: [KEEP_DRAFT_LABEL] });
});

test("createAgentPull: draft + label; falls back to a labelled regular PR where drafts are unsupported", async () => {
  const calls: any[] = [];
  const gh: any = { createPull: async (_r: string, p: any) => { calls.push(["pull", p.draft ?? false]); return { number: 1, base: { repo: { full_name: "me/r" } } }; }, addLabelToPr: async (_p: any, l: string) => { calls.push(["label", l]); return [true, ""]; } };
  await createAgentPull(gh, "me/r", { title: "t", body: "b", head: "h", base: "main" }, { draft: true, labels: [KEEP_DRAFT_LABEL] }, () => {});
  expect(calls).toEqual([["pull", true], ["label", KEEP_DRAFT_LABEL]]);
  calls.length = 0;
  let first = true;
  gh.createPull = async (_r: string, p: any) => { if (first) { first = false; throw new Error("Draft pull requests are not supported in this repository."); } calls.push(["pull", p.draft ?? false]); return { number: 2, base: { repo: { full_name: "me/r" } } }; };
  await createAgentPull(gh, "me/r", { title: "t", body: "b", head: "h", base: "main" }, { draft: true, labels: [KEEP_DRAFT_LABEL] }, () => {});
  expect(calls).toEqual([["pull", false], ["label", KEEP_DRAFT_LABEL]]);
  gh.createPull = async () => { throw new Error("Validation Failed"); };
  await expect(createAgentPull(gh, "me/r", { title: "t", body: "b", head: "h", base: "main" }, { draft: true, labels: [] }, () => {})).rejects.toThrow("Validation Failed");
});

test("review gate never marks a keep-draft PR ready, even when the review approves", async () => {
  const calls: string[] = [];
  const gh: any = { createStatus: async () => {}, setDraft: async (_p: any, d: boolean) => { calls.push(`draft:${d}`); }, removeLabel: async () => {} };
  const approved = mkVerdict({ findings: [], verdict: APPROVE, summary: "ok" });
  const p = (labels: any[]) => ({ number: 1, draft: true, labels, head: { sha: "s" }, base: { repo: { full_name: "me/r" } } }) as any;
  await applyGate(p([{ name: KEEP_DRAFT_LABEL }]), gh, approved, true, () => {});
  expect(calls).toEqual([]);
  await applyGate(p([]), gh, approved, true, () => {});
  expect(calls).toEqual(["draft:false"]);
});

test("agent contract: off by default; refreshes skills + global AGENTS.md, caches, keeps the old copy on failure", async () => {
  const home = tmp(); let calls = 0, fail = false;
  const runner: any = async (cmd: string[], o: any) => {
    calls++;
    if (fail) return { code: 1, stdout: "", stderr: "network down", timedOut: false };
    if (cmd[1] === "clone") { const dst = cmd[cmd.length - 1]; mkdirSync(join(dst, ".git"), { recursive: true }); mkdirSync(join(dst, ".agents", "skills", "code-review"), { recursive: true });
      writeFileSync(join(dst, ".agents", "skills", "code-review", "SKILL.md"), "skill"); writeFileSync(join(dst, ".agents", "AGENTS.md"), "global rules"); }
    expect(o.env.GITHUB_TOKEN).toBeUndefined(); // public clone: credentials never reach git
    return { code: 0, stdout: cmd[1] === "rev-parse" ? "1234567890abcdef" : "", stderr: "", timedOut: false };
  };
  expect((await ensureContract(() => {}, { home, runner })).source).toBe("disabled");
  process.env.AGENT_CONTRACT_REFRESH = "true";
  const old = join(home, ".config", "opencode", "skills", "stale"); mkdirSync(old, { recursive: true });
  const c = await ensureContract(() => {}, { home, runner, now: 1 });
  expect(c).toEqual({ sha: "1234567890abcdef", source: "fresh" });
  expect(readFileSync(join(home, ".config", "opencode", "AGENTS.md"), "utf8")).toBe("global rules");
  expect(existsSync(join(home, ".config", "opencode", "skills", "code-review", "SKILL.md"))).toBe(true);
  expect(existsSync(old)).toBe(false); // skills removed upstream disappear
  expect(contractLabel()).toBe("juninmd/skills@1234567");
  const n = calls; await ensureContract(() => {}, { home, runner, now: 2 }); expect(calls).toBe(n); // within TTL: no git
  fail = true;
  const f = await ensureContract(() => {}, { home, runner, now: 2 + 3_600_001 });
  expect(f.source).toBe("cache"); expect(existsSync(join(home, ".config", "opencode", "skills", "code-review", "SKILL.md"))).toBe(true);
});

test("standardizer: every active repo, missing AGENTS.md first, capped per run, never a second open PR", async () => {
  process.env.REPO_STANDARDS_MAX_PRS = "1";
  const repo = (n: string, o: any = {}) => ({ owner: { login: "me" }, full_name: `me/${n}`, name: n, ...o });
  const files: Record<string, string[]> = { "me/a": ["AGENTS.md", ".agents", "CONTRIBUTING.md", "LICENSE"], "me/b": [], "me/c": [], "me/d": [] };
  const gh: any = { getUserRepos: async (o: any) => { expect(o.limit).toBeNull(); return [repo("a"), repo("arch", { archived: true }), repo("fork", { fork: true }), repo("b"), repo("c"), repo("d")]; },
    pathExists: async (r: string, p: string) => (files[r] ?? []).includes(p), getPulls: async (r: string) => (r === "me/b" ? [{ title: "[agent/x] Standardize b Quality & Intelligence" }] : []) };
  const a: any = new IntelligenceStandardizerAgent(base(gh)); const opened: string[] = [];
  a.loadTaskInstructions = () => "i"; a.runOpencodeOnRepo = async (r: string) => { opened.push(r); return { pr_url: "u" }; };
  const r = await a.run();
  expect(opened).toEqual(["me/c"]);
  const reason = Object.fromEntries(r.skipped.map((x: any) => [x.repository, x.reason]));
  expect(reason).toEqual({ "me/b": "pr_already_open", "me/d": "run_cap_reached", "me/a": "already_standardized" });
});
