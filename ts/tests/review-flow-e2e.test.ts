import { afterEach, beforeEach, expect, test } from "bun:test";
import { chmodSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fallbackVerdict, runReview, verifyPendingFix } from "../src/agents/pr_assistant/review-flow.ts";
import { resetModelCache } from "../src/agents/pr_assistant/review-models.ts";
import { clonePrHead, cleanupStaleReviewDirs, litellmBase, localDiff, resetTrace, lastTrace, reviewModel, reviewTimeout, runOpencode, writeOpencodeConfig } from "../src/agents/pr_assistant/review-workspace.ts";
import { REQUEST_CHANGES } from "../src/agents/pr_assistant/review-verdict.ts";
import { tmp } from "./helpers.ts";
import { existsSync, readFileSync, utimesSync } from "node:fs";

const saved = { ...process.env };
beforeEach(() => resetModelCache());
afterEach(() => { for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k]; Object.assign(process.env, saved); resetModelCache(); resetTrace(); });
const sh = async (cwd: string, ...args: string[]) => { const p = Bun.spawn(args, { cwd, stdout: "pipe", stderr: "pipe" }); const out = await new Response(p.stdout).text(); await p.exited; return out.trim(); };

/** Local bare "GitHub" (https://github.com/o/r.git → file://…), a fake `opencode` on PATH and an isolated HOME. */
async function world(mode: { reviewVerdict: string; fixPatch?: string; fixReview?: string }) {
  const root = tmp(), remote = join(root, "r.git"), seedDir = join(root, "seed"), bin = join(root, "bin"), home = join(root, "home");
  mkdirSync(bin); mkdirSync(home);
  await sh(root, "git", "init", "-q", "--bare", remote);
  await sh(root, "git", "clone", "-q", remote, seedDir);
  await sh(seedDir, "git", "config", "user.email", "t@t"); await sh(seedDir, "git", "config", "user.name", "t");
  writeFileSync(join(seedDir, "a.txt"), "1\n"); await sh(seedDir, "git", "add", "-A"); await sh(seedDir, "git", "commit", "-qm", "base"); await sh(seedDir, "git", "push", "-q", "origin", "HEAD:main");
  await sh(seedDir, "git", "checkout", "-q", "-b", "feature"); writeFileSync(join(seedDir, "a.txt"), "1\nbug\n"); await sh(seedDir, "git", "commit", "-qam", "feat"); await sh(seedDir, "git", "push", "-q", "origin", "feature");
  writeFileSync(join(root, "gitconfig"), `[url "file://${remote}"]\n\tinsteadOf = https://github.com/o/r.git\n`);
  const replies = { review: mode.reviewVerdict, patch: mode.fixPatch ?? "", fixReview: mode.fixReview ?? '{"verdict":"APPROVE","summary":"fix ok"}' };
  for (const [k, v] of Object.entries(replies)) writeFileSync(join(bin, k + ".txt"), v);
  writeFileSync(join(bin, "opencode"), `#!/bin/sh
D="$(dirname "$0")"
case "$1" in
  models) echo opencode/x-free; exit 0;;
  --version) echo 2.3.0; exit 0;;
esac
case "$6" in
  *"CORREÇÃO AUTOMÁTICA"*) cat "$D/fixReview.txt";;
  *"Gere um patch unificado"*) cat "$D/patch.txt";;
  *) cat "$D/review.txt";;
esac
`); chmodSync(join(bin, "opencode"), 0o755);
  Object.assign(process.env, { PATH: `${bin}:${saved.PATH}`, HOME: home, GIT_CONFIG_GLOBAL: join(root, "gitconfig"), GITHUB_TOKEN: "tok", GITHUB_OWNER: "juninmd", TOKENIX_ENABLED: "false", OPENCODE_REVIEW_MAX_FREE_MODELS: "1" });
  const headSha = await sh(seedDir, "git", "rev-parse", "HEAD");
  const pr = { number: 5, title: "Titulo", body: "### Evidências\nSaída dos testes: 10 passed, 0 failed", user: { login: "juninmd" }, head: { ref: "feature", sha: headSha, repo: { full_name: "o/r" } }, base: { ref: "main", repo: { full_name: "o/r" } } } as any;
  const gh = { getFiles: async () => [{ filename: "a.txt", patch: "@@ -1 +1,2 @@\n 1\n+bug" }] } as any;
  return { root, remote, pr, gh, bin };
}
const PATCH = "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n 1\n-bug\n+fixed\n";
const CHANGES = '{"verdict":"REQUEST_CHANGES","summary":"bug","findings":[{"file":"a.txt","line":2,"severity":"error","issue":"bug here"}]}';

test("e2e: approve path — clone, opencode review, no push", async () => {
  const w = await world({ reviewVerdict: '{"verdict":"APPROVE","summary":"ok"}' });
  const before = await sh(w.remote, "git", "rev-parse", "feature");
  const v = await runReview(w.gh, w.pr, null);
  expect(v?.verdict).toBe("APPROVE"); expect(v?.model).toBe("opencode/x-free"); expect(v?.fixed).toBe(false);
  expect(await sh(w.remote, "git", "rev-parse", "feature")).toBe(before);
});
test("e2e: blocking finding → patch applied, independently approved, pushed to the PR branch", async () => {
  const w = await world({ reviewVerdict: CHANGES, fixPatch: PATCH });
  const v = await runReview(w.gh, w.pr, null);
  expect(v).not.toBeNull(); expect(v!.fixed).toBe(true); expect(v!.verdict).toBe("APPROVE"); expect(v!.commit).toMatch(/^[0-9a-f]{40}$/);
  expect(await sh(w.remote, "git", "rev-parse", "feature")).toBe(v!.commit);
  expect(await sh(w.remote, "git", "show", "feature:a.txt")).toBe("1\nfixed");
  expect(await sh(w.remote, "git", "log", "-1", "--format=%s", "feature")).toMatch(/^fix\(review\):/);
});
test("e2e: fix rejected by the independent review is never pushed", async () => {
  const w = await world({ reviewVerdict: CHANGES, fixPatch: PATCH, fixReview: '{"verdict":"REQUEST_CHANGES","summary":"no","findings":[{"file":"a.txt","severity":"error","issue":"regression"}]}' });
  const before = await sh(w.remote, "git", "rev-parse", "feature");
  const v = await runReview(w.gh, w.pr, null);
  expect(v!.fixed).toBe(false); expect(v!.verdict).toBe(REQUEST_CHANGES);
  expect(await sh(w.remote, "git", "rev-parse", "feature")).toBe(before);
});
test("e2e: autofix disabled keeps the verdict and pushes nothing", async () => {
  const w = await world({ reviewVerdict: CHANGES, fixPatch: PATCH });
  process.env.REVIEW_AUTOFIX_ENABLED = "false";
  const before = await sh(w.remote, "git", "rev-parse", "feature");
  const v = await runReview(w.gh, w.pr, null);
  expect(v!.verdict).toBe(REQUEST_CHANGES); expect(v!.fixed).toBe(false); expect(await sh(w.remote, "git", "rev-parse", "feature")).toBe(before);
});
test("e2e: non-owner author is never auto-fixed", async () => {
  const w = await world({ reviewVerdict: CHANGES, fixPatch: PATCH });
  const before = await sh(w.remote, "git", "rev-parse", "feature");
  const v = await runReview(w.gh, { ...w.pr, user: { login: "dependabot[bot]" } }, null);
  expect(v!.fixed).toBe(false); expect(await sh(w.remote, "git", "rev-parse", "feature")).toBe(before);
});
test("e2e: a blocker whose quoted code does not exist is cleared — no block, no autofix push", async () => {
  const fake = '{"verdict":"REQUEST_CHANGES","summary":"Diff expõe credenciais","findings":[{"file":"a.txt","line":1,"severity":"error","evidence":"rcon_password = admin123","issue":"Credenciais expostas"},{"file":"other/gone.txt","severity":"error","issue":"arquivo removido"}]}';
  const w = await world({ reviewVerdict: fake, fixPatch: PATCH });
  const before = await sh(w.remote, "git", "rev-parse", "feature");
  const v = await runReview(w.gh, w.pr, null);
  expect(v!.verdict).toBe("APPROVE"); expect(v!.findings).toEqual([]); expect(v!.fixed).toBe(false);
  expect(v!.summary).not.toContain("credenciais"); expect(v!.summary).toContain("2 alegação");
  expect(v!.harness).toStartWith("opencode");
  expect(await sh(w.remote, "git", "rev-parse", "feature")).toBe(before);
});
test("e2e: a real blocker keeps its block and gets the line of the quoted code", async () => {
  const real = '{"verdict":"APPROVE","summary":"ok","findings":[{"file":"a.txt","line":40,"severity":"error","issue":"x"},{"file":"a.txt","line":40,"severity":"error","evidence":"+bug   ","issue":"linha bug quebra o parser: entrada 1 gera saída inválida"}]}';
  const w = await world({ reviewVerdict: real });
  process.env.REVIEW_AUTOFIX_ENABLED = "false";
  const v = await runReview(w.gh, w.pr, null);
  // no quote → capped at warn (and line 40 is not in the diff); the quoted one is grounded at line 2 and overrides the model's APPROVE
  expect(v!.verdict).toBe(REQUEST_CHANGES);
  expect(v!.findings.map((f) => [f.line, f.severity])).toEqual([[0, "warn"], [2, "error"]]);
});
test("e2e: generated and lock files are not sent to the model; the summary says so", async () => {
  const w = await world({ reviewVerdict: '{"verdict":"APPROVE","summary":"ok"}' });
  const dir = join(w.root, "more"); await sh(w.root, "git", "clone", "-q", "--branch", "feature", w.remote, dir);
  await sh(dir, "git", "config", "user.email", "t@t"); await sh(dir, "git", "config", "user.name", "t");
  writeFileSync(join(dir, "x.mocks.dart"), "// Mocks generated by Mockito\nSECRET_IN_MOCK\n"); writeFileSync(join(dir, "bun.lock"), "LOCK_BODY\n");
  await sh(dir, "git", "add", "-A"); await sh(dir, "git", "commit", "-qm", "gen"); await sh(dir, "git", "push", "-q", "origin", "feature");
  writeFileSync(join(w.bin, "opencode"), `#!/bin/sh\nD="$(dirname "$0")"\ncase "$1" in models) echo opencode/x-free; exit 0;; --version) echo 2.3.0; exit 0;; esac\nprintf '%s' "$6" >> "$D/prompt.txt"\ncat "$D/review.txt"\n`); chmodSync(join(w.bin, "opencode"), 0o755);
  const gh = { getFiles: async () => [{ filename: "a.txt", patch: "@@ -1 +1,2 @@\n 1\n+bug" }, { filename: "x.mocks.dart", patch: "" }, { filename: "bun.lock", patch: "" }] } as any;
  const v = await runReview(gh, { ...w.pr, head: { ...w.pr.head, sha: await sh(dir, "git", "rev-parse", "HEAD") } }, null);
  const prompt = readFileSync(join(w.bin, "prompt.txt"), "utf8");
  expect(prompt).toContain("+bug"); expect(prompt).not.toContain("SECRET_IN_MOCK"); expect(prompt).not.toContain("LOCK_BODY");
  expect(v!.verdict).toBe("APPROVE"); expect(v!.summary).toContain("ignorados sem revisão: 1 lockfile, 1 gerado");
});
test("workspace: a PR behind its base is diffed against the merge-base, not the base tip", async () => {
  const w = await world({ reviewVerdict: "x" });
  const mergeBase = await sh(w.remote, "git", "rev-parse", "main");
  const dir = join(w.root, "adv"); await sh(w.root, "git", "clone", "-q", "--branch", "main", w.remote, dir);
  await sh(dir, "git", "config", "user.email", "t@t"); await sh(dir, "git", "config", "user.name", "t");
  writeFileSync(join(dir, "b.txt"), "base moved\n"); await sh(dir, "git", "add", "-A"); await sh(dir, "git", "commit", "-qm", "base moves"); await sh(dir, "git", "push", "-q", "origin", "main");
  const stale = await localDiff(await clonePrHead(w.pr, tmp(), "tok"), "main", 1e6);
  expect(stale).toContain("b.txt"); // the old behaviour: the base's new file looks deleted by the PR
  const exact = await localDiff(await clonePrHead(w.pr, tmp(), "tok", mergeBase), "main", 1e6);
  expect(exact).toContain("+bug"); expect(exact).not.toContain("b.txt");
  const fallback = await localDiff(await clonePrHead(w.pr, tmp(), "tok", "0".repeat(40)), "main", 1e6);
  expect(fallback).toContain("+bug"); // unknown merge-base → base tip, never a failed review
});
test("run-review: dependency bots are not asked for evidence; the diff-only path grounds its findings too", async () => {
  const w = await world({ reviewVerdict: '{"verdict":"APPROVE","summary":"ok"}' });
  const bot = await runReview(w.gh, { ...w.pr, body: "Bumps x", user: { login: "dependabot[bot]" } }, null);
  expect(bot!.findings).toEqual([]);
  delete process.env.GITHUB_TOKEN; delete process.env.GH_PAT;
  const ai = { generate: async () => '{"verdict":"REQUEST_CHANGES","summary":"s","findings":[{"file":"a.txt","severity":"error","evidence":"password: admin123","issue":"Credenciais expostas"}]}' };
  const v = await runReview(w.gh, w.pr, ai);
  expect(v!.verdict).toBe("APPROVE"); expect(v!.findings).toEqual([]); expect(v!.harness).toBe("litellm (só diff)");
});
test("run-review: without token falls back to the LiteLLM verdict; without client → null", async () => {
  const w = await world({ reviewVerdict: "x" });
  delete process.env.GITHUB_TOKEN; delete process.env.GH_PAT;
  expect(await runReview(w.gh, w.pr, null)).toBeNull();
  const ai = { generate: async () => '{"verdict":"APPROVE","summary":"ok"}' };
  const v = await runReview(w.gh, w.pr, ai);
  expect(v?.verdict).toBe("APPROVE"); expect(v?.harness).toBe("litellm (só diff)");
  expect((await fallbackVerdict(w.gh, w.pr, { generate: async () => "still not json" }))).toBeNull();
});
test("run-review: evidence warning is appended when the PR body has none", async () => {
  const w = await world({ reviewVerdict: '{"verdict":"APPROVE","summary":"ok"}' });
  const v = await runReview(w.gh, { ...w.pr, body: "sem nada" }, null);
  expect(v!.findings.some((f) => f.file === "(descrição do PR)" && f.severity === "warn")).toBe(true);
});
test("verifyPendingFix: approved / rejected / unavailable honours PIPELINE_FIX_REQUIRE_REVIEW", async () => {
  const w = await world({ reviewVerdict: "x" });
  const dir = join(w.root, "work"); await sh(w.root, "git", "clone", "-q", "--branch", "feature", w.remote, dir);
  await sh(dir, "git", "fetch", "-q", "origin", "main:refs/remotes/origin/main");
  writeFileSync(join(dir, "a.txt"), "1\nchanged\n"); writeFileSync(join(dir, "new.txt"), "n\n");
  const [ok, msg] = await verifyPendingFix(w.gh, dir, w.pr);
  expect(ok).toBe(true); expect(msg).toContain("fix review approved");
  writeFileSync(join(w.bin, "fixReview.txt"), '{"verdict":"REQUEST_CHANGES","summary":"no","findings":[{"file":"a.txt","severity":"error","issue":"regression"}]}');
  const [ok2, msg2] = await verifyPendingFix(w.gh, dir, w.pr);
  expect(ok2).toBe(false); expect(msg2).toContain("fix review rejected"); expect(msg2).toContain("regression");
  writeFileSync(join(w.bin, "fixReview.txt"), "not json");
  expect((await verifyPendingFix(w.gh, dir, w.pr))[0]).toBe(true);
  process.env.PIPELINE_FIX_REQUIRE_REVIEW = "true";
  const [ok3, msg3] = await verifyPendingFix(w.gh, dir, w.pr); expect(ok3).toBe(false); expect(msg3).toContain("unavailable");
});

// --- workspace -----------------------------------------------------------
test("workspace: stale cleanup, base normalisation, defaults, config, diff truncation, clone failure", async () => {
  const root = tmp(); mkdirSync(join(root, "pr-review-old")); mkdirSync(join(root, "pr-review-new"));
  utimesSync(join(root, "pr-review-old"), 0, 0);
  cleanupStaleReviewDirs(root); expect(existsSync(join(root, "pr-review-old"))).toBe(false); expect(existsSync(join(root, "pr-review-new"))).toBe(true);
  process.env.LITELLM_API_BASE = "http://x:4000"; expect(litellmBase()).toBe("http://x:4000/v1");
  process.env.LITELLM_API_BASE = "http://x:4000/v1/"; expect(litellmBase()).toBe("http://x:4000/v1");
  delete process.env.OPENCODE_REVIEW_TIMEOUT; delete process.env.OPENCODE_REVIEW_MODEL;
  expect(reviewTimeout()).toBe(900); expect(reviewModel()).toBe("litellm/cloud/auto");
  process.env.OPENCODE_REVIEW_TIMEOUT = "15"; process.env.OPENCODE_REVIEW_MODEL = "litellm/other"; expect(reviewTimeout()).toBe(15); expect(reviewModel()).toBe("litellm/other");
  process.env.LITELLM_API_BASE = "http://litellm:4000/v1"; const cfg = join(root, "cfg"); writeOpencodeConfig(cfg);
  const text = readFileSync(join(cfg, "opencode.json"), "utf8"); expect(text).toContain("litellm"); expect(text).toContain("cloud/auto"); expect(text).toContain("http://litellm:4000/v1");
  const w = await world({ reviewVerdict: "x" });
  const dir = await clonePrHead(w.pr, tmp(), "tok");
  expect((await localDiff(dir, "main", 10)).length).toBe(10);
  expect(await localDiff(dir, "main", 1e6)).toContain("+bug");
  await expect(clonePrHead({ ...w.pr, head: { ...w.pr.head, ref: "nope" } }, tmp(), "tok")).rejects.toThrow("review clone failed");
});
test("workspace: runOpencode success records a trace; failure/timeouts → null", async () => {
  const w = await world({ reviewVerdict: '{"verdict":"APPROVE"}' });
  resetTrace(); expect(lastTrace()).toBeNull();
  const out = await runOpencode(w.root, "prompt", "m", 5); expect(out).toContain("APPROVE");
  expect(lastTrace()?.harness).toStartWith("opencode"); expect(lastTrace()?.model).toBe("m");
  writeFileSync(join(w.bin, "opencode"), "#!/bin/sh\nexit 1\n"); chmodSync(join(w.bin, "opencode"), 0o755);
  expect(await runOpencode(w.root, "p", "m", 5)).toBeNull();
  writeFileSync(join(w.bin, "opencode"), "#!/bin/sh\nsleep 5\n"); chmodSync(join(w.bin, "opencode"), 0o755);
  expect(await runOpencode(w.root, "p", "m", 0.2)).toBeNull();
});
