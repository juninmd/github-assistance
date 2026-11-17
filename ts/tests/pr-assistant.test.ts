import { expect, test } from "bun:test";
import { PRAssistantAgent, isTrustedAuthor } from "../src/agents/pr_assistant/agent.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { applyGate } from "../src/agents/pr_assistant/review-gate.ts";
import { buildAndSendSummary } from "../src/agents/pr_assistant/telegram-summary.ts";
import { notifyMerged, parseResolutionMsg } from "../src/agents/pr_assistant/notifications.ts";
import { buildMarker, readAttemptState, buildPrompt, summarizeOpencodeOutput } from "../src/agents/pr_assistant/pipeline-fixer.ts";
import { runReview } from "../src/agents/pr_assistant/review-flow.ts";
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
    autonomyPolicyPath: pol, aiClient: null, opencodeReviewActive: false, requireReview: false, ...o });
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
test("runReview blocks on leaked credential before any clone", async () => {
  const secretPatch = '+const k = "ghp_' + "a".repeat(36) + '";';
  const gh = fakeGh(pr(), { getFiles: async () => [{ filename: "a.ts", patch: "@@ -0,0 +1 @@\n" + secretPatch }] });
  const v = await runReview(gh, pr(), null);
  expect(v?.verdict).toBe("REQUEST_CHANGES");
});
test("review budget and slot; semaphore timeout", async () => {
  const log: string[] = [];
  const rr = new ReviewRunner({ gh: fakeGh(pr()), log: (m) => log.push(m), forRepository: () => ({}) as any, active: true, budget: 1, waitSeconds: 0 });
  expect(await rr.acquireSlot(pr())).toBe(true);
  expect(await rr.acquireSlot(pr())).toBe(false); // slot busy (wait 0)
  const s = new Semaphore(1); expect(await s.acquire()).toBe(true); expect(await s.acquire(10)).toBe(false); s.release(); expect(await s.acquire(10)).toBe(true);
});
const emptyResults = () => ({ merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] }) as any;
const SHA = "abcdef0123456789abcdef0123456789abcdef01";
const prS = (o: any = {}) => pr({ head: { sha: SHA, ref: "f", repo: { full_name: "o/r" } }, ...o });
const approvalComment = (verdict: string, sha: string, login = "juninmd") => ({ user: { login }, body: `<!-- opencode-review -->\n## x\n\n**Veredito:** \`${verdict}\` · label \`l\`\n\n<sub>SHA \`${sha.slice(0, 8)}\`</sub>` });
test("review runs BEFORE merge; blocked/deferred/unreviewed review prevents the merge", async () => {
  for (const [outcome, reason] of [["blocked", "review_blocked"], ["deferred", "review_pending"], ["unreviewed", "review_unavailable"]] as const) {
    const p = prS(), gh = fakeGh(p), a = mk(gh, tg(), { requireReview: true });
    a.reviews.runOpencodeReview = async () => outcome;
    const r = emptyResults(); await a.processPr(p, r);
    expect(gh.calls.some((c: any) => c[0] === "merge")).toBe(false);
    expect(r.skipped[0].reason).toBe(reason);
  }
  const p = prS(), gh = fakeGh(p, { getIssueComments: async () => [approvalComment("APPROVE", SHA)] }), a = mk(gh, tg(), { requireReview: true }), order: string[] = [];
  a.reviews.runOpencodeReview = async () => { order.push("review"); return "approved"; };
  gh.mergePr = async () => { order.push("merge"); return [true, "ok"]; };
  await a.processPr(p, emptyResults());
  expect(order).toEqual(["review", "merge"]);
});
test("tryMerge itself refuses without an APPROVE pinned to the current SHA (stale, forged, REQUEST_CHANGES, none)", async () => {
  const cases: [string, any[]][] = [
    ["none", []], ["request changes", [approvalComment("REQUEST_CHANGES", SHA)]], ["stale sha", [approvalComment("APPROVE", "def45678")]],
    ["forged author", [approvalComment("APPROVE", SHA, "rando")]],
    ["approve then request changes", [approvalComment("APPROVE", SHA), approvalComment("REQUEST_CHANGES", SHA)]],
  ];
  for (const [name, comments] of cases) {
    const p = prS(), gh = fakeGh(p, { getIssueComments: async () => comments }), a = mk(gh, tg(), { requireReview: true }), r = emptyResults();
    await a.tryMerge(p, r, []);
    expect([name, gh.calls.some((c: any) => c[0] === "merge")]).toEqual([name, false]);
    expect(r.blocked[0].reason).toBe("review_not_approved");
  }
  const p = prS(), gh = fakeGh(p, { getIssueComments: async () => [approvalComment("APPROVE", SHA)] }), r = emptyResults();
  await mk(gh, tg(), { requireReview: true }).tryMerge(p, r, []);
  expect(r.merged).toHaveLength(1);
});
test("merge blocked when head moves after the approval check", async () => {
  const p = prS(), moved = pr({ head: { sha: "f".repeat(40), ref: "f", repo: { full_name: "o/r" } } });
  const gh = fakeGh(p, { getIssueComments: async () => [approvalComment("APPROVE", SHA)], getPull: async () => moved }), r = emptyResults();
  await mk(gh, tg(), { requireReview: true }).tryMerge(p, r, []);
  expect(r.blocked[0].reason).toBe("sha_changed_after_review"); expect(gh.calls.some((c: any) => c[0] === "merge")).toBe(false);
});
test("review runner: approval is read from the SHA-pinned comment; new push is reviewed again", async () => {
  const mkRr = (comments: any[]) => new ReviewRunner({ gh: fakeGh(prS(), { getIssueComments: async () => comments }), log: () => {}, forRepository: () => ({}) as any, active: true, budget: 0, waitSeconds: 0, reviewers: ["juninmd"] });
  expect(await mkRr([approvalComment("APPROVE", SHA)]).runOpencodeReview(prS())).toBe("approved");
  expect(await mkRr([approvalComment("REQUEST_CHANGES", SHA)]).runOpencodeReview(prS())).toBe("blocked");
  expect(await mkRr([approvalComment("APPROVE", "old11111")]).runOpencodeReview(prS())).toBe("deferred"); // budget 0: needs a new review
  const off = mkRr([]); off.active = false; expect(await off.runOpencodeReview(prS())).toBe("unreviewed");
});
test("telegram summary shows blocked PRs with PT-BR reason, no raw codes", async () => {
  const sent: string[] = [];
  await buildAndSendSummary({ blocked: [{ pr: 3, repository: "o/r", reason: "mergeable_state_unknown" }], skipped: [{ pr: 4, repository: "o/r", reason: "review_blocked" }] } as any, { sendMessage: async (t: string) => { sent.push(t); return true; } } as any, "juninmd");
  expect(sent[0]).toContain("Bloqueados"); expect(sent[0]).toContain("estado de merge desconhecido"); expect(sent[0]).toContain("revisão encontrou problema crítico"); expect(sent[0]).not.toContain("review_blocked");
});
