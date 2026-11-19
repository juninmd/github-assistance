import { afterEach, expect, test } from "bun:test";
import { buildFailureComment, checkPipelineStatus, hasExistingFailureComment } from "../src/agents/pr_assistant/pipeline.ts";
import { getPipelineErrorLogs, tailJobLog } from "../src/agents/pr_assistant/logs.ts";
import { GATE_NAME } from "../src/agents/pr_assistant/review-verdict.ts";

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });
const pr = { number: 1, head: { sha: "abc" }, base: { repo: { full_name: "owner/repo" } }, user: { login: "testuser" } } as any;
const gh = (statuses: any[], checkRuns: any[]) => ({ getCombinedStatus: async () => ({ statuses }), getCheckRuns: async () => checkRuns }) as any;
const run = (name: string, conclusion: string | null, o: any = {}) => ({ name, conclusion, status: conclusion ? "completed" : "in_progress", output: { summary: "x" }, html_url: "", ...o });

test("failure-comment detection and rendering", () => {
  expect(hasExistingFailureComment([{ body: "Some text\n❌ **Pipeline Failure Detected**\nmore" }])).toBe(true);
  expect(hasExistingFailureComment([{ body: "Looks good to me!" }])).toBe(false);
  const c = buildFailureComment(pr, [{ context: "lint", description: "Linting failed", url: "http://lint" }, { context: "test", description: "Tests failed", url: "" }]);
  expect(c).toContain("Hi @testuser"); expect(c).toContain("- **lint**: Linting failed ([details](http://lint))"); expect(c).toContain("- **test**: Tests failed");
});
test("no evidence → success but no_ci", async () => {
  const r = await checkPipelineStatus(gh([], []), pr);
  expect(r).toMatchObject({ state: "success", has_evidence: false, no_ci: true, failed_checks: [] });
});
test("failed commit status and failed check-run block", async () => {
  const a = await checkPipelineStatus(gh([{ state: "failure", context: "CI", description: "CI failed", target_url: "http://ci" }], []), pr);
  expect(a.state).toBe("failure"); expect(a.failed_checks).toHaveLength(1); expect(a.failed_checks[0].context).toBe("CI");
  const b = await checkPipelineStatus(gh([], [run("Tests", "failure", { output: { summary: "Tests failed" }, html_url: "http://tests" })]), pr);
  expect(b.state).toBe("failure"); expect(b.failed_checks[0].context).toBe("Tests");
  const c = await checkPipelineStatus(gh([], [run("Build Validation", "failure", { output: { summary: "Vulnerabilities found" } })]), pr);
  expect(c.state).toBe("failure");
});
test("billing and advisory failures count as passed; mixed still fails", async () => {
  const billing = { output: { summary: "The job was not started because recent account payments have failed or your spending limit needs to be increased." } };
  const a = await checkPipelineStatus(gh([], [run("build", "action_required", billing)]), pr);
  expect(a).toMatchObject({ state: "success", failed_checks: [], billing_checks: ["build"] }); expect(a.success_checks).toContainEqual({ context: "build" });
  const adv = await checkPipelineStatus(gh([], [run("autolabel", "failure", { output: { summary: "Resource not accessible by integration" } })]), pr);
  expect(adv).toMatchObject({ state: "success", failed_checks: [], advisory_checks: ["autolabel"] });
  const mixed = await checkPipelineStatus(gh([], [run("build", "action_required", { output: { summary: "spending limit needs to be increased" } }), run("tests", "failure", { output: { summary: "AssertionError: boom" } })]), pr);
  expect(mixed.state).toBe("failure"); expect(mixed.failed_checks.map((c: any) => c.context)).toEqual(["tests"]); expect(mixed.billing_checks).toEqual(["build"]);
});
test("coverage, pending, cancelled, pending commit status, exceptions", async () => {
  const cov = await checkPipelineStatus(gh([], [run("Coverage", "success", { output: { summary: "Coverage: 84.5%" } })]), pr);
  expect(cov.state).toBe("success"); expect(cov.coverage[0].coverage).toBe(84.5);
  const pend = await checkPipelineStatus(gh([], [run("ci", null, { output: null })]), pr);
  expect(pend.state).toBe("pending"); expect(pend.failed_checks).toHaveLength(0);
  const canc = await checkPipelineStatus(gh([], [run("deploy", "cancelled", { output: null })]), pr);
  expect(canc.state).toBe("failure"); expect(canc.cancelled_checks[0].context).toBe("deploy");
  const ps = await checkPipelineStatus(gh([{ state: "pending", context: "ci/wait", description: "running", target_url: "" }], []), pr);
  expect(ps.state).toBe("pending"); expect(ps.pending_checks).toEqual(["ci/wait"]);
  const err = await checkPipelineStatus({ getCombinedStatus: async () => { throw new Error("API Error"); } } as any, pr);
  expect(err.state).toBe("unknown"); expect(err.failed_checks).toHaveLength(0);
});
test("review gate ignored; skipped/neutral are success", async () => {
  const a = await checkPipelineStatus(gh([], [run(GATE_NAME, "action_required", { output: {} }), run("tests", "success", { output: {} })]), pr);
  expect(a.state).toBe("success"); expect(a.failed_checks).toEqual([]);
  expect((await checkPipelineStatus(gh([], [run("update_release_draft", "skipped", { output: {} })]), pr)).state).toBe("success");
  const n = await checkPipelineStatus(gh([], [run("Pages changed", "neutral", { output: {} }), run("validate", "success", { output: {} })]), pr);
  expect(n.state).toBe("success"); expect(n.failed_checks).toEqual([]);
});

test("billing refusal visible only in annotations (no summary) counts as passed, not failed", async () => {
  const msg = "The job was not started because recent account payments have failed or your spending limit needs to be increased.";
  const g = { getCombinedStatus: async () => ({ statuses: [] }), getCheckRuns: async () => [run("validate", "failure", { id: 7, output: { summary: null, annotations_count: 2 } })],
    paginate: async (path: string) => (path.endsWith("/check-runs/7/annotations") ? [{ message: "runner label notice" }, { message: msg }] : []) } as any;
  const r = await checkPipelineStatus(g, pr);
  expect(r).toMatchObject({ state: "success", failed_checks: [], billing_checks: ["validate"] });
  // a real failure with an unrelated annotation must still fail
  const g2 = { ...g, getCheckRuns: async () => [run("tests", "failure", { id: 8, output: { summary: null, annotations_count: 1 } })], paginate: async () => [{ message: "assertion failed" }] } as any;
  expect((await checkPipelineStatus(g2, pr)).state).toBe("failure");
});

// --- logs ----------------------------------------------------------------
const jobGh = (jobs: any[], runs: any[], checkRuns: any[] = [], annotations: any[] = []) => ({
  paginate: async (path: string) => (path.includes("/actions/runs?") ? runs : path.includes("/jobs") ? jobs : path.includes("/annotations") ? annotations : []),
  getCheckRuns: async () => checkRuns,
}) as any;
const mockLog = (text: string) => { globalThis.fetch = (async () => new Response(text, { status: 200 })) as any; };

test("logs from failed jobs: names, error context, timestamps stripped", async () => {
  mockLog("2024-01-01T00:00:00.0Z line1\n2024-01-01T00:00:01.0Z error: boom\n");
  const r = await getPipelineErrorLogs(jobGh([{ name: "build", conclusion: "failure", id: 11 }, { name: "sonar", conclusion: "failure", id: 12 }, { name: "ok", conclusion: "success", id: 13 }], [{ id: 1, conclusion: "failure" }]), pr, "tkn");
  expect(r.failed_checks).toEqual(expect.arrayContaining(["build", "sonar"])); expect(r.failed_checks).not.toContain("ok");
  expect(r.logs).toContain("error: boom"); expect(r.logs).not.toContain("2024-01-01T00:00:01");
});
test("logs filter journal noise", async () => {
  mockLog(["running cargo test", "error[E0277]: the trait bound is not satisfied", "##[error]Process completed with exit code 1.",
    ...Array.from({ length: 9 }, (_, i) => `Jun 04 15:31:5${i} runnervm agentservice[2254]: module=armour noise`)].join("\n"));
  const r = await getPipelineErrorLogs(jobGh([{ name: "build", conclusion: "failure", id: 11 }], [{ id: 1, conclusion: "failure" }]), pr, "tkn");
  expect(r.logs).toContain("error[E0277]"); expect(r.logs).toContain("##[error]Process completed"); expect(r.logs).not.toContain("module=armour");
});
test("logs fall back to check-run summary + annotations", async () => {
  const g = jobGh([], [], [{ id: 5, name: "pytest", conclusion: "failure", output: { summary: "assert failed in test_x" } }], [{ path: "app.py", start_line: 10, message: "NameError" }]);
  const r = await getPipelineErrorLogs(g, pr, "tkn");
  expect(r.failed_checks).toEqual(["pytest"]); expect(r.logs).toContain("assert failed"); expect(r.logs).toContain("app.py:10 NameError");
});
test("tailJobLog filters branch-fetch noise", () => {
  const out = tailJobLog(["2026-01-01T00:00:00Z  * [new branch] feature-a -> origin/feature-a", "2026-01-01T00:00:01Z  * [new branch] feature-b -> origin/feature-b", "2026-01-01T00:00:02Z npm ERR! test failed"].join("\n"));
  expect(out).not.toContain("new branch"); expect(out).toContain("npm ERR! test failed");
});
