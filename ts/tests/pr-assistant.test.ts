import { expect, test } from "bun:test";
import { PRAssistantAgent, isTrustedAuthor } from "../src/agents/pr_assistant/agent.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { applyGate } from "../src/agents/pr_assistant/review-gate.ts";
import { buildAndSendSummary } from "../src/agents/pr_assistant/telegram-summary.ts";
import { notifyMerged, parseResolutionMsg } from "../src/agents/pr_assistant/notifications.ts";
import { buildMarker, readAttemptState, buildPrompt, summarizeOpencodeOutput } from "../src/agents/pr_assistant/pipeline-fixer.ts";
import { fallbackVerdict, runReview } from "../src/agents/pr_assistant/review-flow.ts";
import { ReviewRunner } from "../src/agents/pr_assistant/review-runner.ts";
import { Semaphore } from "../src/utils/semaphore.ts";
import { mkVerdict, mkFinding } from "../src/agents/pr_assistant/review-verdict.ts";
import { tmp } from "./helpers.ts";
import { join } from "node:path";
import { writeFileSync } from "node:fs";

const pr = (o: any = {}) => ({ number: 7, title: "t", html_url: "u", mergeable: true, mergeable_state: "clean", created_at: "2020-01-01T00:00:00Z", labels: [], user: { login: "juninmd" }, draft: false,
  head: { sha: "abc", ref: "f", repo: { full_name: "o/r" } }, base: { ref: "main", repo: { full_name: "o/r" } }, ...o });
function fakeGh(p: any, over: any = {}) {
  const calls: any[] = [];
  const gh: any = {
    calls, getIssueComments: async () => [], getCombinedStatus: async () => ({ statuses: [] }), getCheckRuns: async () => [{ name: "ci", status: "completed", conclusion: "success" }],
    getPull: async () => p, commentOnPr: async (_p: any, b: string) => { calls.push(["comment", b]); }, addLabelToPr: async () => {}, getLabels: async () => [], createLabel: async () => {},
    updatePrBranch: async () => [true, "", "abc"], mergePr: async (_p: any, m: string, sha: string) => { calls.push(["merge", m, sha]); return [true, "ok"]; },
    acceptReviewSuggestions: async () => [true, "", 0], addAssigneeToPr: async () => [true, "ok"], requestReviewerOnPr: async () => [true, "ok"], getFiles: async () => [],
    createStatus: async (...a: any[]) => { calls.push(["status", a[2].state]); }, setDraft: async (_p: any, d: boolean) => { calls.push(["draft", d]); }, removeLabel: async () => { calls.push(["unlabel"]); },
    ...over,
  };
  return gh;
}
const tg = () => { const sent: string[] = []; return { sent, sendMessage: async (t: string) => { sent.push(t); return true; }, sendPrNotification: async () => {} } as any; };
const mk = (gh: any, t: any, o: any = {}) => {
  const dir = tmp(), pol = join(dir, "a.json");
  writeFileSync(pol, JSON.stringify({ defaults: { mode: "merge", merge: true, require_evidence: true } }));
  return new PRAssistantAgent({ githubClient: gh, julesClient: {} as any, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram: t,
    autonomyPolicyPath: pol, aiClient: null, llmReviewerClient: null, reviewAiClient: null, opencodeReviewActive: false, ...o });
};

test("trusted authors", () => {
  expect(isTrustedAuthor("dependabot[bot]")).toBe(true);
  expect(isTrustedAuthor("evil")).toBe(false);
});
test("green PR is squash-merged with SHA lock", async () => {
  const p = pr(), gh = fakeGh(p), t = tg(), a = mk(gh, t);
  const r = { merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] } as any;
  await a.processPr(p, r);
  expect(gh.calls.find((c: any) => c[0] === "merge")).toEqual(["merge", "squash", "abc"]);
  expect(r.merged).toHaveLength(1);
});
test("young, labeled, untrusted skip", async () => {
  const a = mk(fakeGh(pr()), tg());
  const r = () => ({ merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] }) as any;
  let x = r(); await a.processPr(pr({ created_at: new Date().toISOString() }), x); expect(x.skipped[0].reason).toBe("pr_too_young");
  x = r(); await a.processPr(pr({ labels: [{ name: "auto-merge-skip" }] }), x); expect(x.skipped[0].reason).toBe("auto-merge-skip");
  x = r(); await a.processPr(pr({ user: { login: "rando" } }), x); expect(x.skipped[0].reason).toBe("untrusted_author");
});
test("failing CI warns once and skips; no merge", async () => {
  const p = pr(), gh = fakeGh(p, { getCheckRuns: async () => [{ name: "ci", status: "completed", conclusion: "failure" }] }), a = mk(gh, tg());
  const r = { merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] } as any;
  await a.processPr(p, r);
  expect(r.pipeline_failures).toHaveLength(1);
  expect(r.skipped.at(-1).reason).toBe("pipeline_failure");
  expect(gh.calls.some((c: any) => c[0] === "merge")).toBe(false);
});
test("conflicts skip with notification; simulation never merges", async () => {
  const p = pr({ mergeable: false }), gh = fakeGh(p), t = tg(), a = mk(gh, t);
  const r = { merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] } as any;
  await a.processPr(p, r);
  expect(r.skipped.at(-1).reason).toBe("has_conflicts");
  expect(t.sent.some((s: string) => s.includes("CONFLITO"))).toBe(true);
  const gh2 = fakeGh(pr()), a2 = mk(gh2, tg(), { simulationMode: true }), r2 = { merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] } as any;
  await a2.processPr(pr(), r2);
  expect(r2.skipped.at(-1).reason).toBe("simulation");
});
test("autonomy observe blocks merge", async () => {
  const p = pr(), gh = fakeGh(p), a = mk(gh, tg());
  a.autonomy.forRepository = () => ({ mode: "observe", merge: false, max_attempts: 3, require_evidence: true, required_checks: [], allowed_paths: [] });
  const r = { merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] } as any;
  await a.processPr(p, r);
  expect(r.blocked[0].reason).toBe("autonomy_mode:observe");
});
test("run aggregates and sends summary", async () => {
  const p = pr(), gh = fakeGh(p, { searchPrs: async () => [{}], getPrFromIssue: async () => p }), t = tg(), a = mk(gh, t);
  const r = await a.run();
  expect(r.merged).toHaveLength(1);
  expect(t.sent.at(-1)).toContain("PR ASSISTANT SUMMARY");
});
test("review gate: block → draft+failure; approve → success+ready", async () => {
  const gh = fakeGh(pr()), log = () => {};
  await applyGate(pr(), gh, mkVerdict({ verdict: "REQUEST_CHANGES", summary: "x", findings: [mkFinding({ severity: "error", issue: "bad" })] }), true, log);
  expect(gh.calls.map((c: any) => c[0])).toEqual(["draft", "status"]);
  const gh2 = fakeGh(pr({ draft: true }));
  await applyGate(pr({ draft: true }), gh2, mkVerdict({ verdict: "APPROVE", summary: "ok" }), true, log);
  expect(gh2.calls.map((c: any) => c[0])).toEqual(["status", "draft", "unlabel"]);
  const gh3 = fakeGh(pr());
  await applyGate(pr(), gh3, mkVerdict({ verdict: "APPROVE", summary: "ok" }), false, log);
  expect(gh3.calls).toEqual([]);
});
test("summary, notifications, markers", async () => {
  const t = tg();
  await buildAndSendSummary({ merged: [], skipped: [] }, t, "me"); expect(t.sent).toHaveLength(0);
  await buildAndSendSummary({ merged: [{ repository: "o/r", pr: 1, title: "x" }], skipped: [{ repository: "o/r", pr: 2, reason: "r" }] }, t, "me");
  expect(t.sent[0]).toContain("Merged"); expect(t.sent[0]).toContain("Total Processado:</b> <code>2");
  expect(parseResolutionMsg("sum\n**Files:** a\n**Model/Provider:** m")).toEqual(["sum", "a", "m"]);
  const gh = fakeGh(pr());
  await notifyMerged(gh, pr(), [{ body: "<!-- pr-merged -->" }]); expect(gh.calls).toHaveLength(0);
  await notifyMerged(gh, pr(), []); expect(gh.calls).toHaveLength(1);
  expect(readAttemptState([{ body: buildMarker(1, "aa") }, { body: "x" }, { body: buildMarker(2, "bb") }])).toEqual([2, "bb"]);
  expect(buildPrompt("LOG", ["a", "b"])).toContain("failing: a, b.");
  expect(summarizeOpencodeOutput("\x1b[31mred\x1b[0m\n\nlast")).toBe("red | last");
});
test("runReview blocks on leaked credential before any clone; fallback verdict retries", async () => {
  const secretPatch = '+const k = "ghp_' + "a".repeat(36) + '";';
  const gh = fakeGh(pr(), { getFiles: async () => [{ filename: "a.ts", patch: "@@ -0,0 +1 @@\n" + secretPatch }] });
  const v = await runReview(gh, pr(), null);
  expect(v?.verdict).toBe("REQUEST_CHANGES");
  let n = 0;
  const ai = { generate: async () => (++n === 1 ? "garbage" : '{"verdict":"APPROVE","summary":"ok","findings":[]}') };
  const fv = await fallbackVerdict(fakeGh(pr()), pr(), ai);
  expect(fv?.verdict).toBe("APPROVE"); expect(n).toBe(2); expect(fv?.harness).toBe("litellm (só diff)");
  expect(await fallbackVerdict(fakeGh(pr()), pr(), null)).toBeNull();
});
test("review budget and slot; semaphore timeout", async () => {
  const log: string[] = [];
  const rr = new ReviewRunner({ gh: fakeGh(pr()), log: (m) => log.push(m), forRepository: () => ({}) as any, llmClient: null, reviewAi: null, active: true, budget: 1, waitSeconds: 0 });
  expect(await rr.acquireSlot(pr())).toBe(true);
  expect(await rr.acquireSlot(pr())).toBe(false); // slot busy (wait 0)
  const s = new Semaphore(1); expect(await s.acquire()).toBe(true); expect(await s.acquire(10)).toBe(false); s.release(); expect(await s.acquire(10)).toBe(true);
});
const emptyResults = () => ({ merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] }) as any;
test("review runs BEFORE merge; blocked or deferred review prevents the merge", async () => {
  for (const [outcome, reason] of [["blocked", "review_blocked"], ["deferred", "review_pending"]] as const) {
    const p = pr(), gh = fakeGh(p), a = mk(gh, tg()), order: string[] = [];
    a.reviews.runOpencodeReview = async () => { order.push("review"); return outcome; };
    const r = emptyResults(); await a.processPr(p, r);
    expect(gh.calls.some((c: any) => c[0] === "merge")).toBe(false);
    expect(r.skipped[0].reason).toBe(reason);
  }
  const p = pr(), gh = fakeGh(p), a = mk(gh, tg()), order: string[] = [];
  a.reviews.runOpencodeReview = async () => { order.push("review"); return "none"; };
  gh.mergePr = async () => { order.push("merge"); return [true, "ok"]; };
  await a.processPr(p, emptyResults());
  expect(order).toEqual(["review", "merge"]);
});
test("existing review comment with critical label keeps blocking", async () => {
  const rr = new ReviewRunner({ gh: fakeGh(pr(), { getIssueComments: async () => [{ body: "<!-- opencode-review -->" }] }), log: () => {}, forRepository: () => ({}) as any, llmClient: null, reviewAi: null, active: true, budget: 1, waitSeconds: 0 });
  expect(await rr.runOpencodeReview(pr({ labels: [{ name: "review/critical" }] }))).toBe("blocked");
  expect(await rr.runOpencodeReview(pr())).toBe("none");
});
test("telegram summary shows blocked PRs with PT-BR reason, no raw codes", async () => {
  const sent: string[] = [];
  await buildAndSendSummary({ blocked: [{ pr: 3, repository: "o/r", reason: "mergeable_state_unknown" }], skipped: [{ pr: 4, repository: "o/r", reason: "review_blocked" }] } as any, { sendMessage: async (t: string) => { sent.push(t); return true; } } as any, "juninmd");
  expect(sent[0]).toContain("Bloqueados"); expect(sent[0]).toContain("estado de merge desconhecido"); expect(sent[0]).toContain("revisão encontrou problema crítico"); expect(sent[0]).not.toContain("review_blocked");
});
