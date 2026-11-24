import { expect, test } from "bun:test";
import { PRAssistantAgent } from "../src/agents/pr_assistant/agent.ts";
import { mergeBlockLabel } from "../src/agents/pr_assistant/merge-block.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { tmp } from "./helpers.ts";
import { join } from "node:path";
import { writeFileSync } from "node:fs";

const pr = (o: any = {}) => ({ number: 77, title: "t", html_url: "u", mergeable: true, mergeable_state: "clean", created_at: "2020-01-01T00:00:00Z", labels: [], user: { login: "juninmd" }, draft: false,
  head: { sha: "abc", ref: "f", repo: { full_name: "o/r" } }, base: { ref: "main", repo: { full_name: "o/r" } }, ...o });
function fakeGh(p: any, over: any = {}) {
  const calls: any[] = [];
  const gh: any = {
    calls, pathExists: async () => true, getIssueComments: async () => [], getCombinedStatus: async () => ({ statuses: [] }), getCheckRuns: async () => [{ name: "ci", status: "completed", conclusion: "success" }],
    getPull: async () => p, commentOnPr: async () => {}, addLabelToPr: async () => {}, getLabels: async () => [], createLabel: async () => {},
    updatePrBranch: async () => [true, "", "abc"], mergePr: async (_p: any, m: string, sha: string) => { calls.push(["merge", m, sha]); return [true, "ok"]; },
    acceptReviewSuggestions: async () => [true, "", 0], addAssigneeToPr: async () => [true, "ok"], requestReviewerOnPr: async () => [true, "ok"], getFiles: async () => [],
    createStatus: async () => {}, setDraft: async () => {}, removeLabel: async () => {},
    ...over,
  };
  return gh;
}
const mk = (gh: any) => {
  const pol = join(tmp(), "a.json");
  writeFileSync(pol, JSON.stringify({ defaults: { mode: "merge", merge: true, require_evidence: true } }));
  return new PRAssistantAgent({ githubClient: gh, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram: { sendMessage: async () => true, sendPrNotification: async () => {} } as any,
    autonomyPolicyPath: pol, aiClient: null, opencodeReviewActive: false, requireReview: false,
    localChecks: async () => [true, "stub"], resolveConflicts: async () => [false, "stub"] });
};
const results = () => ({ merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] }) as any;
const merged = (gh: any) => gh.calls.some((c: any) => c[0] === "merge");

test("owner's hold labels are recognised in any spelling the owner is likely to type", () => {
  for (const name of ["do-not-merge", "DO NOT MERGE", "do_not_merge", "Do-Not-Merge", "dont-merge", "don't merge", "wip", "WIP", "work in progress", "auto-merge-skip"])
    expect(mergeBlockLabel(pr({ labels: [{ name }] }))).toBe(name);
  expect(mergeBlockLabel(pr({ labels: ["do-not-merge"] }))).toBe("do-not-merge");
});
test("unrelated labels that only contain a hold word do not block the merge", () => {
  for (const name of ["merge-conflict", "wipe-cache", "docs", "dependencies", "keep-draft"])
    expect(mergeBlockLabel(pr({ labels: [{ name }] }))).toBeNull();
  expect(mergeBlockLabel(pr({ labels: undefined }))).toBeNull();
});
// Regression: juninmd/mika#77 carried `do-not-merge` and was squash-merged anyway.
test("a green, trusted PR labeled do-not-merge is never merged", async () => {
  const p = pr({ labels: [{ name: "do-not-merge" }] }), gh = fakeGh(p), r = results();
  await mk(gh).processPr(p, r);
  expect(merged(gh)).toBe(false);
  expect(r.merged).toHaveLength(0);
  expect(r.skipped[0].reason).toBe("merge_block_label: do-not-merge");
});
test("an owner /merge does not override a do-not-merge label", async () => {
  const p = pr({ labels: [{ name: "WIP" }] });
  const gh = fakeGh(p, { getIssueComments: async () => [{ user: { login: "juninmd" }, body: "/merge", created_at: new Date().toISOString() }] });
  await mk(gh).processPr(p, results());
  expect(merged(gh)).toBe(false);
});
test("a label added while the run is in progress still stops the merge", async () => {
  const snapshot = pr(), fresh = pr({ labels: [{ name: "do not merge" }] }), gh = fakeGh(fresh), r = results();
  await mk(gh).processPr(snapshot, r);
  expect(merged(gh)).toBe(false);
  expect(r.blocked.at(-1)?.reason ?? r.skipped.at(-1)?.reason).toBe("merge_block_label: do not merge");
});
