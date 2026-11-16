import { expect, test, beforeEach, afterEach } from "bun:test";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { LLMUsage, instrument, TokenBudgetExceeded, estimateTokens } from "../src/ai/usage.ts";
import { AIClient, extractCodeBlock, extractJsonObject, getAiClient } from "../src/ai/client.ts";
import { recordRun, recordTrace, summarize, summarizeSkills, summarizeTokenix } from "../src/insight/cost.ts";
import { GitHubRateBudgetExhausted, GitHubRateLimiter, type RedisLike } from "../src/github/ratelimit.ts";
import { GithubClient, GithubError } from "../src/github/client.ts";
import { applySuggestions, collectSuggestions, normalizeLogin } from "../src/github/review-suggestions.ts";
import { redactSecrets, scrubEnv, authConfigArgs, githubCloneUrl } from "../src/utils/secure-git.ts";
import { scanClone, scanText, redactText } from "../src/utils/secret-scan.ts";
import { withRetry, HttpError } from "../src/utils/retry.ts";
import { run } from "../src/utils/proc.ts";
import { TelegramNotifier } from "../src/notifications/telegram.ts";
import { configureEnviron, CONFIG_ENV } from "../src/utils/tokenix.ts";

process.env.AI_CACHE = "0";
const tmp = () => mkdtempSync(join(tmpdir(), "l1-"));
const realFetch = globalThis.fetch;
let calls: { url: string; init?: any }[] = [];
const mockFetch = (fn: (url: string, init?: any) => Response | Promise<Response>) => {
  calls = [];
  globalThis.fetch = (async (u: any, init?: any) => { calls.push({ url: String(u), init }); return fn(String(u), init); }) as any;
};
afterEach(() => { globalThis.fetch = realFetch; });

class Fake extends AIClient {
  n = 0; constructor(public reply = "ok") { super(); this.model = "m"; }
  protected async complete() { this.n++; return this.reply; }
}

// --- AI -----------------------------------------------------------------------
test("extractCodeBlock / extractJsonObject", () => {
  expect(extractCodeBlock("x\n```ts\nconst a=1\n```\ny")).toBe("const a=1\n");
  expect(extractCodeBlock("plain")).toBe("plain\n");
  expect(extractJsonObject('blah {"a": {"b": 1}} tail')).toEqual({ a: { b: 1 } });
  expect(extractJsonObject('```json\n{"a":1}\n```')).toEqual({ a: 1 });
  expect(extractJsonObject("nothing")).toBeNull();
});

test("usage: cache hit saves tokens; budget enforced", async () => {
  process.env.AI_CACHE = "1";
  const u = new LLMUsage();
  const c = new Fake("answer");
  const run1 = () => instrument("generate", c, ["prompt"], () => (c as any).complete(), u);
  expect(await run1()).toBe("answer");
  expect(await run1()).toBe("answer");
  expect(c.n).toBe(1);
  const s = u.snapshot();
  expect([s.llm_calls, s.llm_cache_hits, s.llm_cache_hit_rate]).toEqual([1, 1, 50]);
  expect(s.llm_tokens_saved_est).toBeGreaterThan(0);
  process.env.AI_TOKEN_BUDGET = "1";
  try { await expect(instrument("generate", c, ["x".repeat(100)], async () => "y", u)).rejects.toBeInstanceOf(TokenBudgetExceeded); }
  finally { delete process.env.AI_TOKEN_BUDGET; }
  process.env.AI_CACHE = "0";
  expect(estimateTokens("abcde")).toBe(2);
  const start = u.snapshot();
  u.record("generate", 4, 4, 1);
  expect(u.delta(start).llm_calls).toBe(1);
});

test("usage: sqlite cache persists across instances", () => {
  const p = join(tmp(), "c.db");
  new LLMUsage(4, p).put("k", "v");
  expect(new LLMUsage(4, p).get("k")).toBe("v");
});

test("classifySecretFinding and analyzePrClosure parse model JSON, fail safe", async () => {
  expect(await new Fake('{"action":"REMOVE_FROM_HISTORY","reason":"real"}').classifySecretFinding({ file: "a" })).toEqual({ action: "REMOVE_FROM_HISTORY", reason: "real" });
  expect((await new Fake("garbage").classifySecretFinding({})).action).toBe("IGNORE");
  expect((await new Fake('{"action":"NUKE"}').classifySecretFinding({})).action).toBe("IGNORE");
  expect(await new Fake('{"should_close": true, "reason": "r"}').analyzePrClosure("p", "m", "c")).toEqual([true, "r"]);
  expect(await new Fake("nope").analyzePrClosure("p", "m", "c")).toEqual([false, ""]);
});

test("providers: openai-compatible, ollama, gemini over HTTP", async () => {
  mockFetch(() => Response.json({ choices: [{ message: { content: " hi " } }] }));
  const oa = getAiClient("litellm", { apiKey: '"k"', baseUrl: "https://proxy.example/", model: "cloud/auto" });
  expect(await oa.generate("p1")).toBe("hi");
  expect(calls[0].url).toBe("https://proxy.example/v1/chat/completions");
  expect(calls[0].init.headers.Authorization).toBe("Bearer k");
  mockFetch(() => Response.json({ response: " llama " }));
  expect(await getAiClient("ollama", { model: "q" }).generate("p2")).toBe("llama");
  mockFetch(() => Response.json({ candidates: [{ content: { parts: [{ text: "gem" }] } }] }));
  expect(await getAiClient("gemini", { apiKey: "g" }).generate("p3")).toBe("gem");
  expect(() => getAiClient("zzz")).toThrow("Unknown AI provider");
  await expect(getAiClient("openai", { apiKey: null }).generate("p4x")).rejects.toThrow("OPENAI_API_KEY is required");
});

test("cost ledger: records, summarizes, never throws", () => {
  const p = join(tmp(), "l", "usage.jsonl");
  process.env.AI_USAGE_LOG = p;
  try {
    recordRun({ agent_name: "a", llm_calls: 2, llm_tokens_in_est: 10, llm_tokens_out_est: 5 });
    recordRun({ agent_name: "none" });
    recordTrace({ harness: "opencode + tokenix 1", model: "m", skills_used: ["s1"], skills_available: ["s1", "s2"], tokens_in: 100, tokens_out: 50, cost: null, tools: ["tokenix_find", "read"] });
    expect(summarize(p)[0]).toMatchObject({ agent: "opencode", tokens: 150 });
    expect(summarize(p).find((r) => r.agent === "a")).toMatchObject({ runs: 1, calls: 2, tokens: 15 });
    expect(summarizeSkills(p)[0]).toMatchObject({ skill: "s1", runs: 1 });
    expect(summarizeTokenix(p).with).toMatchObject({ runs: 1, tokenix_calls: 1, mean_tokens: 150 });
    expect(summarize("/nope")).toEqual([]);
  } finally { delete process.env.AI_USAGE_LOG; }
});

// --- GitHub ------------------------------------------------------------------------
class FakeRedis implements RedisLike {
  m = new Map<string, number>(); ttlv = 100; fail = false;
  async incrby(k: string, n: number) { if (this.fail) throw new Error("down"); this.m.set(k, (this.m.get(k) ?? 0) + n); return this.m.get(k)!; }
  async expire() { return 1; } async ttl() { return this.ttlv; }
  async get(k: string) { return this.m.has(k) ? String(this.m.get(k)) : null; }
  async set(k: string, v: any) { this.m.set(k, Number(v)); }
}
test("rate limiter: budget, wait, exhaustion, fail-open, observe reconciliation", async () => {
  const r = new FakeRedis(); let slept = 0;
  const lim = new GitHubRateLimiter(r, "tok", 2, 3600, 30, "ns", async (ms) => { slept = ms; });
  await lim.acquire("/a"); await lim.acquire("/b");
  r.ttlv = 10; await lim.acquire("/c"); expect(slept).toBe(10_000);
  r.ttlv = 999; await expect(lim.acquire("/d")).rejects.toBeInstanceOf(GitHubRateBudgetExhausted);
  await lim.acquire("/rate_limit");
  await lim.observe(new Headers({ "x-ratelimit-limit": "5000", "x-ratelimit-remaining": "10" }));
  expect([...r.m.values()][0]).toBe(4990);
  const bad = new FakeRedis(); bad.fail = true;
  await new GitHubRateLimiter(bad, "t", 1).acquire("/x"); // fail-open
});

const PR_BASE = { number: 7, base: { repo: { full_name: "a/b" } }, head: { sha: "abc12345", ref: "f", repo: { full_name: "a/b" } } };
const gh = () => new GithubClient("t", null);
test("merge: sha guard, passes sha lock, refreshes on base-modified 405", async () => {
  mockFetch((u, init) => init.method === "GET" ? Response.json({ ...PR_BASE, head: { sha: "other999" } }) : Response.json({}));
  const [ok, msg] = await gh().mergePr(PR_BASE, "squash", "abc12345");
  expect(ok).toBe(false); expect(msg).toContain("HEAD changed");
  let puts = 0;
  mockFetch((u, init) => {
    if (init.method === "GET") return Response.json(PR_BASE);
    puts++;
    return puts === 1 ? Response.json({ message: "Base branch was modified. Review and try the merge again." }, { status: 405 }) : Response.json({ merged: true });
  });
  const r = await gh().mergePr(PR_BASE, "squash", "abc12345");
  expect(r).toEqual([true, "Merged successfully after refreshing PR base"]);
  const put = calls.find((c) => c.init.method === "PUT")!;
  expect(JSON.parse(put.init.body)).toEqual({ merge_method: "squash", sha: "abc12345" });
  mockFetch((u, init) => init.method === "GET" ? Response.json(PR_BASE) : Response.json({ message: "nope" }, { status: 409 }));
  expect((await gh().mergePr(PR_BASE))[0]).toBe(false);
});

test("comment redacts secrets; label/assign return [ok,msg]; paginate follows Link", async () => {
  mockFetch(() => Response.json({}));
  await gh().commentOnPr(PR_BASE, "token ghp_" + "a".repeat(30));
  expect(JSON.parse(calls[0].init.body).body).toBe("token REDACTED");
  mockFetch(() => Response.json({ message: "Validation Failed" }, { status: 422 }));
  expect(await gh().addLabelToPr(PR_BASE, "x")).toEqual([false, "422 Validation Failed"]);
  let page = 0;
  mockFetch(() => { page++; return Response.json([page], { headers: page === 1 ? { link: '<https://api.github.com/next>; rel="next"' } : {} }); });
  expect(await gh().paginate("/x")).toEqual([1, 2]);
  mockFetch(() => new Response("boom", { status: 404 }));
  await expect(gh().get("/x")).rejects.toBeInstanceOf(GithubError);
  expect(() => new GithubClient(null, null)).toThrow;
});

test("review suggestions: collect from trusted bots only and apply bottom-up", () => {
  const body = "```suggestion\nNEW\n```";
  const comments = [
    { user: { login: "Copilot[bot]" }, path: "f.ts", line: 2, body },
    { user: { login: "human" }, path: "f.ts", line: 1, body },
    { user: { login: "copilot" }, path: "f.ts", line: 4, start_line: 3, body: "```suggestion\nA\nB\nC\n```" },
  ];
  const m = collectSuggestions(comments, new Set([normalizeLogin("COPILOT[bot]")]));
  expect(m.get("f.ts")!.length).toBe(2);
  const { text, authors } = applySuggestions("l1\nl2\nl3\nl4\nl5", m.get("f.ts")!);
  expect(text).toBe("l1\nNEW\nA\nB\nC\nl5");
  expect(authors.sort()).toEqual(["Copilot[bot]", "copilot"]);
});

// --- security utils -----------------------------------------------------------------
test("redactSecrets / scrubEnv / auth args", () => {
  expect(redactSecrets("https://x-access-token:abcdefghij@github.com/a")).not.toContain("abcdefghij");
  expect(redactSecrets("password=supersecret123")).toBe("password=REDACTED");
  expect(redactSecrets("Authorization: Bearer xyz")).toBe("Authorization: Bearer REDACTED");
  const env = scrubEnv({ GITHUB_TOKEN: "a", LITELLM_API_KEY: "keep", MY_SECRET: "s", PATH: "/bin", FOO_PAT: "p" });
  expect(env).toEqual({ LITELLM_API_KEY: "keep", PATH: "/bin" });
  expect(authConfigArgs("tok")[1]).toContain("extraheader=Authorization: Basic ");
  expect(authConfigArgs("tok").join(" ")).not.toContain("tok ");
  expect(githubCloneUrl("a/b")).toBe("https://github.com/a/b.git");
});

test("secret scan: patterns, known secrets, clone scan, redact", async () => {
  const pat = "ghp_" + "A".repeat(30);
  expect(scanText(`a\nx = ${pat}`, { known: [] })).toEqual([{ rule_id: "github-pat", line: 2 }]);
  expect(scanText("ghp_your_token_here", { known: [] })).toEqual([]);
  expect(scanText("v=" + "z".repeat(24), { known: ["z".repeat(24)] })[0]).toEqual({ rule_id: "known-secret", line: 1 });
  const d = tmp();
  writeFileSync(join(d, "a.env"), `K=${pat}\n`);
  mkdirSync(join(d, ".git")); writeFileSync(join(d, ".git", "c"), pat);
  const saved = [process.env.PUSH_GUARD_GITLEAKS, process.env.PUSH_GUARD_SAST];
  process.env.PUSH_GUARD_GITLEAKS = "off"; process.env.PUSH_GUARD_SAST = "off";
  try {
    const f = await scanClone(d, { known: [] });
    expect(f).toEqual([{ file: "a.env", rule_id: "github-pat", line: 1 }]);
    expect(JSON.stringify(f)).not.toContain(pat);
  } finally { process.env.PUSH_GUARD_GITLEAKS = saved[0]; process.env.PUSH_GUARD_SAST = saved[1]; if (saved[0] === undefined) delete process.env.PUSH_GUARD_GITLEAKS; if (saved[1] === undefined) delete process.env.PUSH_GUARD_SAST; }
  expect(redactText(`x ${pat}`, { known: [] })).toBe("x [REDACTED]");
  expect(await scanClone("/does/not/exist")).toEqual([]);
});

// --- plumbing ---------------------------------------------------------------------
test("retry: retries retryable, stops on others", async () => {
  let n = 0;
  expect(await withRetry(async () => { if (++n < 3) throw new HttpError(503, "x"); return "ok"; }, { sleep: async () => {} })).toBe("ok");
  n = 0;
  await expect(withRetry(async () => { n++; throw new HttpError(404, "x"); }, { sleep: async () => {} })).rejects.toThrow();
  expect(n).toBe(1);
});

test("proc.run: output, exit code, timeout kills the group, missing binary", async () => {
  expect((await run(["sh", "-c", "echo hi; echo err >&2; exit 3"]))).toMatchObject({ code: 3, stdout: "hi\n", stderr: "err\n" });
  const t0 = Date.now();
  const r = await run(["sh", "-c", "sleep 30"], { timeoutMs: 300 });
  expect(r.timedOut).toBe(true);
  expect(Date.now() - t0).toBeLessThan(5000);
  expect((await run(["definitely-not-a-binary"])).code).toBe(127);
  expect((await run(["sh", "-c", "pwd"], { cwd: "/tmp" })).stdout.trim()).toBe("/tmp");
});

test("telegram: escape, split with part markers", () => {
  expect(TelegramNotifier.escapeHtml("<a&b>")).toBe("&lt;a&amp;b&gt;");
  expect(TelegramNotifier.escape("a.b")).toBe("a\\.b");
  const t = new TelegramNotifier("t", "c");
  const parts = t.split(("line\n").repeat(2000));
  expect(parts.length).toBeGreaterThan(1);
  expect(parts[0]).toContain(`(parte 1/${parts.length})`);
  expect(parts.every((p) => p.length <= 4096)).toBe(true);
  expect(new TelegramNotifier(null, null).enabled).toBe(false);
});

test("telegram: send retries on 5xx and falls back from HTML parse errors", async () => {
  let n = 0;
  mockFetch(() => (++n === 1 ? new Response("{}", { status: 503 }) : Response.json({ ok: true })));
  const ok = await new TelegramNotifier("t", "c", "pfx").sendMessage("hi");
  expect(ok).toBe(true);
  expect(JSON.parse(calls[0].init.body).text).toContain("<b>pfx</b>");
  mockFetch((u, i) => (JSON.parse(i.body).parse_mode ? new Response("can't parse entities", { status: 400 }) : Response.json({})));
  expect(await new TelegramNotifier("t", "c").sendMessage("<bad")).toBe(true);
});

test("tokenix configureEnviron merges MCP entry, respects invalid config", () => {
  const bin = Bun.which("sh")!;
  process.env.TOKENIX_BIN = bin;
  try {
    const env: Record<string, string | undefined> = { [CONFIG_ENV]: '{"x":1}' };
    expect(configureEnviron(env)).toBe(true);
    expect(JSON.parse(env[CONFIG_ENV]!)).toMatchObject({ x: 1, mcp: { tokenix: { type: "local", command: [bin, "mcp"] } } });
    expect(configureEnviron({ [CONFIG_ENV]: "{bad" })).toBe(false);
    process.env.TOKENIX_ENABLED = "false";
    expect(configureEnviron({})).toBe(false);
  } finally { delete process.env.TOKENIX_BIN; delete process.env.TOKENIX_ENABLED; }
});
