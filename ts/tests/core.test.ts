import { AGENTS_BY_NAME } from "../src/agents/catalog.ts";
import { expect, test, afterEach } from "bun:test";
import { mkdtempSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createDefaultOrchestrator, AgentOrchestrator } from "../src/agents/orchestration.ts";
import { AgentPriority } from "../src/agents/catalog.ts";
import { runAll as batchRunAll } from "../src/agents/batch-runner.ts";
import { isSemantic, semanticMessage } from "../src/agents/core/commit-message.ts";
import { AgentMetrics } from "../src/agents/core/metrics.ts";
import { formatDuration, saveResults, sendExecutionReport } from "../src/agents/core/reporting.ts";
import { buildOriginMetadata, buildPrBody, getInstructionsSection, loadTaskInstructions, assignOwner, requestReviewOwner, ensureLabel } from "../src/agents/core/utils.ts";
import { RepositoryManager } from "../src/agents/core/repo-manager.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { TelegramNotifier } from "../src/notifications/telegram.ts";
import { runAgent, isFailedResult, anyBatchFailure } from "../src/run-agent.ts";
import { runHealthChecks } from "../src/health.ts";
import { isPorted, buildAiConfig, createAgent } from "../src/agents/registry.ts";
import { parseEvents, harnessVersion } from "../src/agents/opencode/trace.ts";
import { setForcedModel, resetModelsCache, selectFreeOpencodeModel } from "../src/agents/opencode/models.ts";
import { testSettings } from "./helpers.ts";

process.env.AI_CACHE = "0";
const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

test("orchestrator: batches respect deps; cycles and missing deps fail loudly; external deps allowed", () => {
  const o = new AgentOrchestrator();
  o.register("scan", AgentPriority.CRITICAL); o.register("remove", AgentPriority.CRITICAL, ["scan"]); o.register("sla", AgentPriority.LOW);
  const b = o.parallelBatches(["remove", "scan", "sla"]);
  expect(b[0]).toContain("scan");
  expect(b[1]).toEqual(["remove"]);
  expect(o.parallelBatches(["remove"])).toEqual([["remove"]]); // dep outside run: not a cycle
  const c = new AgentOrchestrator(); c.register("a", AgentPriority.LOW, ["b"]); c.register("b", AgentPriority.LOW, ["a"]);
  expect(() => c.parallelBatches(["a", "b"])).toThrow("circular dependency");
  const m = new AgentOrchestrator(); m.register("a", AgentPriority.LOW, ["ghost"]);
  expect(() => m.parallelBatches(["a"])).toThrow("missing dependencies: ghost");
  // The real fleet has no cross-agent dependencies left (secret-guard runs scan -> remove internally): priority only.
  expect(createDefaultOrchestrator().order(["builder", "secret-guard", "pr-assistant"])).toEqual(["secret-guard", "pr-assistant", "builder"]);
});

test("batch runner: dependents blocked when dependency failed; AI agents skipped without ENABLE_AI", async () => {
  const s = await testSettings();
  const ran: string[] = [];
  const res = await batchRunAll(s, async (n) => { ran.push(n); return n === "secret-guard" ? { error: "boom" } : { ok: true }; });
  for (const ai of ["builder", "repo-standards", "project-creator"]) expect(ran).not.toContain(ai); // requires AI (off)
  expect(ran).toContain("secret-guard"); // scanning needs no AI; its AI stage is skipped inside the agent
  expect(res["secret-guard"].error).toBe("boom");
  expect(res["pr-assistant"]).toEqual({ ok: true }); // one failure does not stop independent agents
  const s3 = await testSettings({ PR_ASSISTANT_ENABLED: "false" });
  expect(Object.keys(await batchRunAll(s3, async () => ({})))).not.toContain("pr-assistant");
});

test("commit messages are semantic", () => {
  expect(isSemantic("feat(x): y")).toBe(true);
  expect(isSemantic("Update stuff")).toBe(false);
  expect(semanticMessage("feat", "My Agent!", "Add Thing.", "body")).toBe("feat(my-agent): add Thing\n\nbody".replace("add Thing", "add Thing"));
  expect(semanticMessage("weird", "", "")).toBe("chore: atualiza código");
  expect(semanticMessage("fix", "s", "x".repeat(200)).split("\n")[0].length).toBeLessThanOrEqual(72);
});

test("metrics: success rate, usage delta, summary", () => {
  const m = new AgentMetrics("a");
  m.incrementProcessed(3); m.incrementFailed(1); m.addError("e"); m.addWarning("w");
  const f = m.finalize();
  expect([f.success_rate, f.total_items, f.error_count, f.warning_count]).toEqual([75, 4, 1, 1]);
  expect(f).toHaveProperty("llm_calls");
  expect(m.summary()).toContain("Success Rate: 75%");
  expect(new AgentMetrics("b").finalize().success_rate).toBe(100);
});

test("reporting: telegram report shapes; pr-assistant silent; results saved", async () => {
  const sent: string[] = [];
  const tg = new TelegramNotifier("t", "c"); tg.sendMessage = async (t: string) => { sent.push(t); return true; };
  await sendExecutionReport(tg, "pr-assistant", {});
  expect(sent).toEqual([]);
  await sendExecutionReport(tg, "x", { error: "boom\nsecond" });
  expect(sent[0]).toContain("FALHA CRÍTICA"); expect(sent[0]).not.toContain("second");
  await sendExecutionReport(tg, "senior-developer", { security_tasks: [1, 2], processed: [1], failed: [{ repository: "a/b", error: "bad" }], _metrics: { duration_seconds: 75, success_rate: 50 } });
  expect(sent[1]).toContain("Segurança: <b>2</b>"); expect(sent[1]).toContain("1m15s"); expect(sent[1]).toContain("a/b");
  await sendExecutionReport(tg, "all", { a: { error: "e" }, b: {} });
  expect(sent[2]).toContain("✅ <code>1</code> | ❌ <code>1</code>");
  expect(formatDuration(5)).toBe("5s");
  const dir = mkdtempSync(join(tmpdir(), "r-"));
  const f = saveResults("x", { a: 1 }, dir);
  expect(JSON.parse(readFileSync(f, "utf8"))).toEqual({ a: 1 });
  expect(readdirSync(dir).length).toBe(1);
});

test("agent utils: PR body, sections, templates, same-day UTC-3", () => {
  expect(buildPrBody("a", "t", "x".repeat(2000)).includes("x".repeat(1500))).toBe(true);
  expect(buildPrBody("a", "t", "x".repeat(2000)).includes("x".repeat(1501))).toBe(false);
  expect(buildOriginMetadata("ag", "m")).toContain("`ag`");
  expect(getInstructionsSection("# A\nx\n## Mission\nm1\n### sub\nm2\n## Next\nn", "mission")).toBe("m1\n### sub\nm2");
  expect(getInstructionsSection("", "x")).toBe("");
  expect(loadTaskInstructions("nonexistent-agent")).toBe("");
});

test("owner assignment and review request are best-effort and idempotent", async () => {
  const calls: string[] = [];
  const gh: any = { addAssigneeToPr: async (_: any, l: string) => { calls.push("assign:" + l); return [true, ""]; }, requestReviewerOnPr: async (_: any, l: string) => { calls.push("review:" + l); return [true, ""]; } };
  expect(await assignOwner(gh, { assignees: [{ login: "Juninmd" }] }, "juninmd")).toBe(true);
  expect(calls).toEqual([]);
  await assignOwner(gh, { assignees: [] }, "juninmd");
  expect(await requestReviewOwner(gh, { user: { login: "juninmd" } }, "juninmd")).toBe(false);
  expect(await requestReviewOwner(gh, { user: { login: "bot" }, requested_reviewers: [] }, "juninmd")).toBe(true);
  expect(calls).toEqual(["assign:juninmd", "review:juninmd"]);
  const bad: any = { addAssigneeToPr: async () => { throw new Error("x"); } };
  expect(await assignOwner(bad, {}, "j")).toBe(false);
});

test("ensureLabel creates only when missing (case-insensitive)", async () => {
  const created: any[] = [];
  const gh: any = { paginate: async () => [{ name: "Roadmap" }], post: async (_: string, b: any) => { created.push(b); } };
  await ensureLabel(gh, "a/b", "roadmap", "fff"); await ensureLabel(gh, "a/b", "new", "000");
  expect(created.map((c) => c.name)).toEqual(["new"]);
});

test("repository manager: owner scope, sorted by recency, info cached", async () => {
  const f = join(mkdtempSync(join(tmpdir(), "al-")), "r.json");
  await Bun.write(f, JSON.stringify({ repositories: ["juninmd/old", "other/x"] }));
  let infoCalls = 0;
  const gh: any = {
    getUserRepos: async () => [{ full_name: "juninmd/new", owner: { login: "juninmd" }, updated_at: "2026-02-01T00:00:00Z" }, { full_name: "foo/bar", owner: { login: "foo" }, updated_at: "2026-03-01T00:00:00Z" }],
    getRepo: async () => { infoCalls++; return { updated_at: "2025-01-01T00:00:00Z" }; },
  };
  const rm = new RepositoryManager(gh, new RepositoryAllowlist(f), "juninmd", () => {});
  expect(await rm.getAllowedRepositories(false)).toEqual(["juninmd/old", "juninmd/new"]);
  expect(rm.canWorkOn("other/x", false)).toBe(false);
  expect(rm.canWorkOn("juninmd/q", true)).toBe(false);
  expect(await rm.getInfo("other/x")).toBeNull();
  await rm.getInfo("juninmd/old"); await rm.getInfo("juninmd/old");
  expect(infoCalls).toBe(1);
});

test("run-agent: wraps results, failure semantics, unported agent errors cleanly", async () => {
  const s = await testSettings();
  AGENTS_BY_NAME.set("ghost", { ...AGENTS_BY_NAME.get("branch-cleaner")!, name: "ghost" } as any);
  const r = await runAgent("ghost", s, { save: false });
  AGENTS_BY_NAME.delete("ghost");
  expect(r.error).toContain("ainda não foi portado");
  expect(isFailedResult(r)).toBe(true);
  expect(r._run_result.status).toBe("failed");
  expect(isFailedResult({ _run_result: { status: "blocked" } })).toBe(false);
  expect(anyBatchFailure({ a: {}, b: { error: "x" } })).toBe(true);
  expect(anyBatchFailure({ a: {} })).toBe(false);
  await expect(createAgent("zzz", s)).rejects.toThrow("unknown agent");
  expect(isPorted("flow-watch")).toBe(true);
  expect(isPorted("ghost")).toBe(false);
});

test("health checks: AI provider keys, telegram warning", async () => {
  const s = await testSettings({ ENABLE_AI: "true", AI_PROVIDER: "gemini" });
  expect(runHealthChecks(s, "builder").errors).toContain("AI_PROVIDER=gemini but GEMINI_API_KEY is missing");
  // Former names resolve to their stage: the remover stage needs AI keys, the scanner stage does not.
  expect(runHealthChecks(s, "secret-remover").errors).toContain("AI_PROVIDER=gemini but GEMINI_API_KEY is missing");
  expect(runHealthChecks(s, "security-scanner").errors).toEqual([]);
  const ok = runHealthChecks(await testSettings({ ENABLE_AI: "true", AI_PROVIDER: "litellm", LITELLM_API_KEY: "k" }), "builder");
  expect(ok.ok).toBe(true); expect(ok.warnings[0]).toContain("Telegram");
  expect(runHealthChecks(await testSettings(), "pr-sla").ok).toBe(true);
});

test("AI config: provider override resets model to provider default", async () => {
  const s = await testSettings({ LITELLM_API_KEY: "k" });
  expect(buildAiConfig(s)).toMatchObject({ provider: "litellm", model: "cloud/auto", config: { apiKey: "k" } });
  expect(buildAiConfig(s, "gemini")).toMatchObject({ provider: "gemini", model: "gemini-2.5-flash" });
  expect(buildAiConfig(s, "gemini", "custom").model).toBe("custom");
});

test("opencode trace: parses skills/tokens/cost; falls back to raw text", () => {
  const out = [
    JSON.stringify({ type: "text", part: { text: "hello" } }),
    JSON.stringify({ type: "tool_use", part: { tool: "skill", state: { input: { name: "review" } } } }),
    JSON.stringify({ type: "tool_use", part: { tool: "tokenix_find", state: { input: {} } } }),
    JSON.stringify({ type: "step_finish", part: { tokens: { input: 10, output: 5 }, cost: 0.5 } }),
    "not json",
  ].join("\n");
  const [text, f] = parseEvents(out);
  expect(text).toBe("hello");
  expect(f).toEqual({ skills_used: ["review"], tools: ["skill", "tokenix_find"], tokens_in: 10, tokens_out: 5, cost: 0.5, structured: true });
  expect(parseEvents("plain output")).toEqual(["plain output", expect.objectContaining({ structured: false })]);
});

test("opencode model selection: env > forced > preferred; harness version tolerant of missing binary", async () => {
  resetModelsCache();
  process.env.OPENCODE_MODEL = "x/y";
  expect(await selectFreeOpencodeModel(0)).toBe("x/y");
  delete process.env.OPENCODE_MODEL;
  setForcedModel("forced/m");
  expect(await selectFreeOpencodeModel(3)).toBe("forced/m");
  resetModelsCache();
  expect(await harnessVersion("/definitely/not/here")).toBe("");
});
