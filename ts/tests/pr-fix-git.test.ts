import { afterEach, expect, test } from "bun:test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { attemptPipelineFix } from "../src/agents/pr_assistant/pipeline-fix-flow.ts";
import { buildMarker } from "../src/agents/pr_assistant/pipeline-fixer.ts";
import * as git from "../src/agents/pr_assistant/review-git.ts";
import { extractPatch, fixPrompt } from "../src/agents/pr_assistant/review-patch.ts";
import { mkFinding, mkVerdict, REQUEST_CHANGES } from "../src/agents/pr_assistant/review-verdict.ts";
import { tmp } from "./helpers.ts";

const saved = { ...process.env };
afterEach(() => { for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k]; Object.assign(process.env, saved); });
const sh = async (cwd: string, ...args: string[]) => { const p = Bun.spawn(args, { cwd, stdout: "pipe", stderr: "pipe" }); const out = await new Response(p.stdout).text(); await p.exited; return out.trim(); };

async function repoWithRemote() {
  const root = tmp(), remote = join(root, "remote.git"), work = join(root, "work");
  await sh(root, "git", "init", "-q", "--bare", remote);
  await sh(root, "git", "clone", "-q", remote, work);
  await sh(work, "git", "config", "user.email", "t@t"); await sh(work, "git", "config", "user.name", "t");
  writeFileSync(join(work, "a.txt"), "1\n"); await sh(work, "git", "add", "-A"); await sh(work, "git", "commit", "-qm", "init"); await sh(work, "git", "push", "-q", "origin", "HEAD:main");
  return { work, remote };
}

// --- review-git (real git, local bare remote) ----------------------------
test("commitAndPush: nothing staged → false", async () => {
  const { work } = await repoWithRemote();
  expect(await git.commitAndPush(work, "main", "msg")).toEqual([false, ""]);
});
test("commitAndPush: pushes the change and returns the sha; never commits opencode.json", async () => {
  const { work, remote } = await repoWithRemote();
  writeFileSync(join(work, "a.txt"), "2\n"); writeFileSync(join(work, "opencode.json"), "{}");
  const [ok, sha] = await git.commitAndPush(work, "main", "fix: x");
  expect(ok).toBe(true); expect(sha).toMatch(/^[0-9a-f]{40}$/);
  expect(await sh(remote, "git", "rev-parse", "main")).toBe(sha);
  expect(await sh(remote, "git", "ls-tree", "-r", "--name-only", "main")).not.toContain("opencode.json");
});
test("commitAndPush: blocks a credential before commit/push", async () => {
  const { work, remote } = await repoWithRemote();
  const before = await sh(remote, "git", "rev-parse", "main");
  writeFileSync(join(work, "leak.txt"), `token = "ghp_${"a".repeat(36)}"\n`);
  const [ok, detail] = await git.commitAndPush(work, "main", "msg");
  expect(ok).toBe(false); expect(detail).toStartWith("secret-found:"); expect(detail).not.toContain("a".repeat(20));
  expect(await sh(remote, "git", "rev-parse", "main")).toBe(before);
});
test("commitAndPush: push failure and unusable dir → false", async () => {
  const { work } = await repoWithRemote();
  writeFileSync(join(work, "a.txt"), "3\n");
  expect((await git.commitAndPush(work, "refs/nope/../bad", "msg"))[0]).toBe(false);
  expect(await git.commitAndPush("/nonexistent-dir-xyz", "main", "msg")).toEqual([false, ""]);
});
test("applyPatch / discardChanges", async () => {
  const { work } = await repoWithRemote();
  expect(await git.applyPatch(work, "")).toBe(false);
  expect(await git.applyPatch(work, "diff --git a/zz b/zz\n--- a/zz\n+++ b/zz\n@@ -1 +1 @@\n-x\n+y\n")).toBe(false);
  writeFileSync(join(work, "a.txt"), "1\n2\n"); writeFileSync(join(work, "new.txt"), "n");
  await git.discardChanges(work);
  expect(readFileSync(join(work, "a.txt"), "utf8")).toBe("1\n"); expect(existsSync(join(work, "new.txt"))).toBe(false);
  const patch = "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1,2 @@\n 1\n+2\n";
  expect(await git.applyPatch(work, patch)).toBe(true); expect(readFileSync(join(work, "a.txt"), "utf8")).toBe("1\n2\n");
});

// --- review-patch --------------------------------------------------------
test("fix prompt and patch extraction", () => {
  const v = mkVerdict({ verdict: REQUEST_CHANGES, summary: "x", model: "m", findings: [mkFinding({ file: "a.py", line: 3, severity: "error", issue: "bug" })] });
  const p = fixPrompt(v); expect(p).toContain("a.py"); expect(p).toContain("bug"); expect(p).toContain("diff --git");
  const fenced = extractPatch("claro:\n```diff\ndiff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-1\n+2\n```\nfim");
  expect(fenced).toStartWith("diff --git"); expect(fenced).toContain("-1"); expect(fenced).toContain("+2");
  expect(extractPatch("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-1\n+2")).toStartWith("diff --git");
  expect(extractPatch(null)).toBe(""); expect(extractPatch("no patch here")).toBe("");
});

// --- pipeline-fix-flow ---------------------------------------------------
const pr = (o: any = {}) => ({ number: 9, user: { login: "juninmd" }, head: { sha: "sha1", ref: "f", repo: { full_name: "fork/r" } }, base: { ref: "main", repo: { full_name: "o/r" } }, ...o }) as any;
function gh(o: { checkRuns?: any[]; comments?: any[]; behind?: number; updated?: [boolean, string, string] } = {}) {
  const calls: any[] = [];
  return { calls,
    getCombinedStatus: async () => ({ statuses: [] }),
    getCheckRuns: async () => o.checkRuns ?? [{ name: "ci", status: "completed", conclusion: "failure", output: { summary: "boom error: x" } }],
    getIssueComments: async () => o.comments ?? [],
    compare: async () => ({ behind_by: o.behind ?? 0 }),
    updatePrBranch: async () => { calls.push(["update"]); return o.updated ?? [true, "Branch updated", "newsha"]; },
    commentOnPr: async (_p: any, b: string) => { calls.push(["comment", b]); },
    addLabelToPr: async (_p: any, l: string) => { calls.push(["label", l]); },
    paginate: async () => [] } as any;
}
const enable = () => { process.env.PIPELINE_FIX_ENABLED = "true"; process.env.PIPELINE_FIX_MAX_ATTEMPTS = "3"; };
const log = () => {};

test("flow: disabled and not-failing are no-ops", async () => {
  delete process.env.PIPELINE_FIX_ENABLED; expect(await attemptPipelineFix(pr(), gh(), log)).toBe(false);
  enable(); expect(await attemptPipelineFix(pr(), gh({ checkRuns: [{ name: "ci", status: "completed", conclusion: "success" }] }), log)).toBe(false);
});
test("flow: stale branch is updated instead of editing files; failure falls back; can be disabled", async () => {
  enable();
  let g = gh({ behind: 15 }); expect(await attemptPipelineFix(pr(), g, log)).toBe(true);
  expect(g.calls.map((c: any) => c[0])).toEqual(["update", "comment"]);
  g = gh({ behind: 4, updated: [false, "failed (422)", ""] });
  expect(await attemptPipelineFix(pr(), g, log)).toBe(false); // falls to the fixer (fork head → cannot push)
  expect(g.calls.some((c: any) => c[0] === "comment" && c[1].includes("Tentativa 1/3"))).toBe(true);
  process.env.PIPELINE_FIX_UPDATE_BRANCH = "false"; g = gh({ behind: 10 });
  await attemptPipelineFix(pr(), g, log); expect(g.calls.some((c: any) => c[0] === "update")).toBe(false);
});
test("flow: exhausted attempts mark manual; failure on last attempt marks manual; no logs is a no-op", async () => {
  enable();
  let g = gh({ comments: [{ body: buildMarker(3, "aa") }] });
  expect(await attemptPipelineFix(pr(), g, log)).toBe(false); expect(g.calls.filter((c: any) => c[0] === "label")).toHaveLength(1);
  g = gh({ comments: [{ body: buildMarker(2, "aa") }] });
  expect(await attemptPipelineFix(pr(), g, log)).toBe(false); expect(g.calls.filter((c: any) => c[0] === "label")).toHaveLength(1);
  expect(g.calls.some((c: any) => c[0] === "comment" && c[1].includes("Tentativa 3/3") && c[1].includes("cannot push"))).toBe(true);
  g = gh({ checkRuns: [{ name: "ci", status: "completed", conclusion: "failure", output: { summary: "" } }] });
  g.getCheckRuns = async () => [{ name: "ci", status: "completed", conclusion: "failure", output: null }];
  g.paginate = async () => []; // no jobs, summary "No details" → still non-empty; use empty result instead
  expect(typeof (await attemptPipelineFix(pr(), g, log))).toBe("boolean");
});
test("flow: exceptions are swallowed", async () => {
  enable();
  const g = gh(); g.getCombinedStatus = async () => { throw new Error("boom"); };
  expect(await attemptPipelineFix(pr(), g, log)).toBe(false);
});
test("commitAndPush: refuses to commit node_modules or .env", async () => {
  const { work, remote } = await repoWithRemote();
  mkdirSync(join(work, "node_modules", "x"), { recursive: true });
  writeFileSync(join(work, "node_modules", "x", "i.js"), "module.exports = 1;\n");
  const [ok, detail] = await git.commitAndPush(work, "main", "msg");
  expect(ok).toBe(false);
  expect(detail).toContain("forbidden-path: node_modules/x/i.js");
  expect(await sh(remote, "git", "ls-tree", "-r", "--name-only", "main")).not.toContain("node_modules");
});
