import { afterEach, expect, test } from "bun:test";
import { chmodSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import * as bg from "../src/agents/pr_assistant/billing-gate.ts";
import * as cs from "../src/agents/pr_assistant/comment-scan.ts";
import * as cg from "../src/agents/pr_assistant/credential-gate.ts";
import { commitsBehind } from "../src/agents/pr_assistant/branch-staleness.ts";
import { MergePolicy } from "../src/agents/pr_assistant/merge-policy.ts";
import { isJules, isOwner, shouldAutofix } from "../src/agents/pr_assistant/review-authors.ts";
import * as flags from "../src/agents/pr_assistant/review-flags.ts";
import { opencodeReviewEnabled } from "../src/agents/pr_assistant/opencode-reviewer.ts";
import { candidateModels, freeOpencodeModels, resetModelCache } from "../src/agents/pr_assistant/review-models.ts";
import { REQUEST_CHANGES, blocks } from "../src/agents/pr_assistant/review-verdict.ts";
import { tmp } from "./helpers.ts";

const saved = { ...process.env };
afterEach(() => { for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k]; Object.assign(process.env, saved); resetModelCache(); });
const TOKEN = "ghp_" + "c".repeat(30);
const file = (filename: string, patch: string, status = "modified") => ({ filename, patch, status });
const pr = (files: any[]) => ({ number: 9, base: { ref: "master", repo: { full_name: "o/private" } }, head: { ref: "feature", sha: "abc" } });
const ghFiles = (files: any[]) => ({ getFiles: async () => files }) as any;

// --- billing gate --------------------------------------------------------
test("billing: blocked flag", () => {
  expect(bg.isBillingBlocked({ billing_checks: ["x"] })).toBe(true);
  expect(bg.isBillingBlocked({ billing_checks: [] })).toBe(false);
  expect(bg.isBillingBlocked({})).toBe(false);
});
test("billing: scan looks only at additions and never echoes the value", async () => {
  const token = "ghp_" + "a".repeat(30);
  const out = await bg.scanAddedLines(ghFiles([file("a.py", `@@\n-old = '${token}'\n+safe = 1\n`), file("b.py", `@@\n+x = '${token}'\n`)]), pr([]) as any);
  expect(out.map((f) => f.file)).toEqual(["b.py"]);
  expect(JSON.stringify(out)).not.toContain("a".repeat(10));
});
test("billing: forbidden files; deletions ignored", async () => {
  for (const p of [".env", "a/.env.production", "id_rsa", "certs/server.pem", "k/app.key"]) expect(bg.isForbiddenFile(p)).toBe(true);
  for (const p of [".env.example", "tests/fixtures/x.pem", "src/app.py"]) expect(bg.isForbiddenFile(p)).toBe(false);
  const out = await bg.scanAddedLines(ghFiles([file("prod/.env", "@@\n+A=1\n", "added"), file("old/.env", "", "removed")]), pr([]) as any);
  expect(out.map((f) => [f.file, f.rule_id])).toEqual([["prod/.env", "forbidden-secret-file"]]);
});
test("billing: disclaimer builds, detects itself", () => {
  const body = bg.buildDisclaimer(["ci / test"], "abcdef123");
  expect(body).toContain(bg.BILLING_DISCLAIMER_MARKER); expect(body.toLowerCase()).toContain("billing");
  expect(bg.hasDisclaimer([{ body }])).toBe(true); expect(bg.hasDisclaimer([{ body: "x" }])).toBe(false);
});

// --- comment scan --------------------------------------------------------
const c = (id: number, body: string) => ({ id, body, html_url: `https://x/${id}` });
test("comment-scan: warns once without echoing value; own warning not rescanned", () => {
  const comments = [c(1, `my token ${TOKEN}`), c(2, "all good")];
  const warns = cs.pendingWarnings(comments);
  expect(warns).toHaveLength(1); expect(warns[0]).not.toContain(TOKEN); expect(warns[0]).toContain("github-pat");
  comments.push(c(3, warns[0]!));
  expect(cs.pendingWarnings(comments)).toEqual([]);
  expect(cs.findExposedComments([c(5, cs.buildWarning(1, "u", ["r"]) + TOKEN)])).toEqual([]);
});

// --- credential gate -----------------------------------------------------
test("credential gate: added lines, clean text, blocking verdict", () => {
  const patch = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old line\n+new line\n context";
  expect(cg.addedLines(patch)).toBe("new line");
  expect(cg.credentialVerdict("print('hello')")).toBeNull();
  const v = cg.credentialVerdict(`TOKEN = '${"ghp_" + "A".repeat(36)}'`)!;
  expect(v.verdict).toBe(REQUEST_CHANGES); expect(blocks(v, "error")).toBe(true);
  expect(v.findings.every((f) => !f.issue.includes("A".repeat(36)))).toBe(true);
});

// --- merge policy --------------------------------------------------------
const MERGE = { mode: "merge", merge: true, require_evidence: true, max_attempts: 3, required_checks: [] as string[], allowed_paths: [] as string[] };
const status = (state = "success", o: { failed?: number; pending?: number; cancelled?: number; evidence?: boolean } = {}) => ({
  state, failed_checks: Array(o.failed ?? 0).fill({ context: "ci" }), pending_checks: Array(o.pending ?? 0).fill({ context: "ci" }), cancelled_checks: Array(o.cancelled ?? 0).fill({ context: "ci" }),
  success_checks: (o.evidence ?? true) ? [{ context: "ci" }] : [], has_evidence: o.evidence ?? true, checks: { total: 1 },
});
const evalP = (st: any, over: any = {}) => new MergePolicy().evaluate({ status: st, expectedSha: "abc", currentSha: "abc", autonomy: MERGE, ...over });
test("merge policy matrix", () => {
  expect(evalP(status()).action).toBe("merge");
  expect(evalP(status(), { currentSha: "def" })).toMatchObject({ action: "blocked", reasons: expect.arrayContaining(["sha_changed"]) });
  expect(evalP(status("failure", { failed: 1 }))).toMatchObject({ action: "blocked", reasons: expect.arrayContaining(["checks_failed"]) });
  expect(evalP(status("pending", { pending: 1 }))).toMatchObject({ action: "wait", reasons: expect.arrayContaining(["checks_pending"]) });
  expect(evalP(status("failure", { cancelled: 1 }))).toMatchObject({ action: "blocked", reasons: expect.arrayContaining(["checks_cancelled"]) });
  expect(evalP(status("unknown"))).toMatchObject({ action: "wait", reasons: expect.arrayContaining(["checks_unknown"]) });
  expect(evalP(status("pending", { evidence: false }))).toMatchObject({ action: "wait", reasons: expect.arrayContaining(["no_evidence"]) });
  const missing = evalP(status(), { autonomy: { ...MERGE, required_checks: ["lint", "test"] } });
  expect(missing.action).toBe("blocked"); expect(missing.reasons.some((r: string) => r.startsWith("missing_checks:"))).toBe(true);
  const observe = { ...MERGE, mode: "observe", merge: false };
  expect(evalP(status(), { autonomy: observe })).toMatchObject({ action: "blocked", reasons: expect.arrayContaining(["autonomy_mode:observe"]) });
  const noCi = { ...status("success", { evidence: false }), no_ci: true, checks: { total: 0 } };
  expect(evalP(noCi).action).toBe("merge");
  expect(evalP(noCi, { autonomy: observe })).toMatchObject({ action: "blocked", reasons: expect.arrayContaining(["autonomy_mode:observe"]) });
});

// --- branch staleness ----------------------------------------------------
test("commitsBehind: value, clamp, unknown, non-int", async () => {
  const gh = (behind: any) => ({ compare: async () => ({ behind_by: behind }) }) as any;
  expect(await commitsBehind(gh(15), pr([]) as any)).toBe(15);
  expect(await commitsBehind(gh(0), pr([]) as any)).toBe(0);
  expect(await commitsBehind(gh(-3), pr([]) as any)).toBe(0);
  expect(await commitsBehind({ compare: async () => { throw new Error("no permission"); } } as any, pr([]) as any)).toBe(0);
  expect(await commitsBehind(gh(undefined), pr([]) as any)).toBe(0);
});

// --- authors & flags -----------------------------------------------------
test("authors", () => {
  for (const a of ["google-labs-jules", "google-labs-jules[bot]", "Jules da Google"]) expect(isJules(a)).toBe(true);
  expect(isJules("juninmd")).toBe(false); expect(isJules(null)).toBe(false);
  process.env.GITHUB_OWNER = "juninmd";
  expect(isOwner("JUNINMD")).toBe(true); expect(isOwner("someone")).toBe(false);
  expect(shouldAutofix("juninmd")).toBe(true); expect(shouldAutofix("google-labs-jules[bot]")).toBe(false); expect(shouldAutofix("dependabot[bot]")).toBe(false);
});
test("flags and reviewer enablement", () => {
  delete process.env.REVIEW_DRY_RUN; delete process.env.REVIEW_GATE_MIN_SEVERITY; delete process.env.OPENCODE_REVIEW_ENABLED;
  expect(flags.reviewDryRun()).toBe(false); process.env.REVIEW_DRY_RUN = "true"; expect(flags.reviewDryRun()).toBe(true);
  expect(flags.gateMinSeverity()).toBe("error"); process.env.REVIEW_GATE_MIN_SEVERITY = "WARN"; expect(flags.gateMinSeverity()).toBe("warn");
  expect(flags.enabled("SOME_FLAG", true)).toBe(true);
  for (const v of ["0", "false", "no", "off", "FALSE"]) { process.env.SOME_FLAG = v; expect(flags.enabled("SOME_FLAG", true)).toBe(false); }
  process.env.SOME_FLAG = "yes"; expect(flags.enabled("SOME_FLAG", false)).toBe(true);
  expect(opencodeReviewEnabled()).toBe(true); process.env.OPENCODE_REVIEW_ENABLED = "false"; expect(opencodeReviewEnabled()).toBe(false);
});

// --- review models (fake `opencode` on PATH) -----------------------------
function fakeOpencode(stdout: string, exit = 0) {
  const dir = tmp(), bin = join(dir, "opencode");
  writeFileSync(bin, `#!/bin/sh\ncat <<'EOF'\n${stdout}\nEOF\nexit ${exit}\n`); chmodSync(bin, 0o755);
  process.env.PATH = `${dir}:${saved.PATH}`;
}
test("models: free filter, fallback, cloud appended, bounds, deepseek first", async () => {
  fakeOpencode("opencode/big-pickle\nopencode/x-free\nopencode/paid");
  expect((await freeOpencodeModels()).sort()).toEqual(["opencode/big-pickle", "opencode/x-free"]);
  process.env.PATH = "/nonexistent"; resetModelCache();
  expect(await freeOpencodeModels()).toEqual(["opencode/big-pickle"]);
  process.env.PATH = saved.PATH;
  fakeOpencode(Array.from({ length: 10 }, (_, i) => `m${i}-free`).join("\n")); resetModelCache();
  process.env.OPENCODE_REVIEW_MODEL = "litellm/cloud/auto"; process.env.OPENCODE_REVIEW_MAX_FREE_MODELS = "2";
  const c2 = await candidateModels(); expect(c2).toHaveLength(3); expect(c2.at(-1)).toBe("litellm/cloud/auto");
  process.env.OPENCODE_REVIEW_MAX_FREE_MODELS = "abc"; expect(await candidateModels()).toHaveLength(4);
  fakeOpencode("opencode/x-free\nopencode/deepseek-v4.1-flash-free\nopencode/big-pickle"); resetModelCache();
  const m = await freeOpencodeModels(); expect(m[0]).toBe("opencode/deepseek-v4.1-flash-free"); expect(m).toHaveLength(3);
});
