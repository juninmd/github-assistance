import { afterEach, expect, test } from "bun:test";
import { join } from "node:path";
import { writeFileSync } from "node:fs";
import { PRAssistantAgent, isTrustedAuthor } from "../src/agents/pr_assistant/agent.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { ReviewRunner } from "../src/agents/pr_assistant/review-runner.ts";
import { ReviewInfraError } from "../src/agents/pr_assistant/review-errors.ts";
import { approvalFor, approvalState } from "../src/agents/pr_assistant/review-approval.ts";
import { fingerprintFiles } from "../src/agents/pr_assistant/diff-fingerprint.ts";
import { buildReviewComment, mkVerdict } from "../src/agents/pr_assistant/review-verdict.ts";
import { decideWaiver, PENDING_MARKER } from "../src/agents/pr_assistant/review-waiver.ts";
import { reviewerLogins, gitIdentity } from "../src/agents/pr_assistant/bot-identity.ts";
import { ownerCommands, mergeCommandValid } from "../src/agents/pr_assistant/owner-commands.ts";
import { evaluateCommentsWithLlm } from "../src/agents/pr_assistant/merge-decision.ts";
import { laneAllowsMerge, realPassedChecks } from "../src/agents/pr_assistant/dependency-lane.ts";
import { scanAddedLines } from "../src/agents/pr_assistant/billing-gate.ts";
import { acquirePrLock, BUSY_LABEL } from "../src/agents/pr_assistant/pr-lock.ts";
import { MANUAL_CONFLICT_LABEL } from "../src/agents/pr_assistant/conflict-flow.ts";
import { tmp } from "./helpers.ts";

const SHA = "abcdef0123456789abcdef0123456789abcdef01";
const T0 = Date.parse("2026-11-20T10:00:00Z");
const iso = (ms: number) => new Date(ms).toISOString();
const pr = (o: any = {}) => ({ number: 7, title: "t", html_url: "u", mergeable: true, mergeable_state: "clean", created_at: "2020-01-01T00:00:00Z", labels: [], user: { login: "juninmd" },
  draft: false, additions: 10, deletions: 2, head: { sha: SHA, ref: "f", repo: { full_name: "o/r" } }, base: { ref: "main", repo: { full_name: "o/r" } }, ...o });
const results = () => ({ merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [], blocked: [] }) as any;
const owner = (body: string, at = T0) => ({ user: { login: "juninmd", type: "User" }, body, created_at: iso(at) });
const files = [{ filename: "src/a.ts", status: "modified", patch: "@@ -1,2 +1,2 @@\n ctx\n-old\n+new" }];
function fakeGh(p: any, over: any = {}) {
  const calls: any[] = [];
  const gh: any = {
    calls, getIssueComments: async () => [], getCombinedStatus: async () => ({ statuses: [] }), getCheckRuns: async () => [{ name: "ci", status: "completed", conclusion: "success" }],
    getPull: async () => p, commentOnPr: async (_p: any, b: string) => { calls.push(["comment", b]); }, addLabelToPr: async (_p: any, l: string) => { calls.push(["label", l]); return [true, ""]; },
    getLabels: async () => [], createLabel: async () => {}, updatePrBranch: async () => [true, "", SHA], getFiles: async () => files, getCommits: async () => [{ sha: SHA, commit: { committer: { date: iso(T0) } } }],
    mergePr: async (_p: any, m: string, sha: string) => { calls.push(["merge", m, sha]); return [true, "ok"]; }, acceptReviewSuggestions: async () => [true, "", 0],
    addAssigneeToPr: async () => [true, "ok"], requestReviewerOnPr: async () => [true, "ok"], createStatus: async () => {}, setDraft: async () => {},
    removeLabel: async (_p: any, l: string) => { calls.push(["unlabel", l]); }, getContents: async () => null, ...over,
  };
  return gh;
}
const tg = () => ({ sent: [] as string[], sendMessage: async () => true, sendPrNotification: async () => {} }) as any;
function agent(gh: any, o: any = {}) {
  const pol = join(tmp(), "a.json");
  writeFileSync(pol, JSON.stringify({ defaults: { mode: "merge", merge: true, require_evidence: true } }));
  return new PRAssistantAgent({ githubClient: gh, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram: tg(), autonomyPolicyPath: pol, aiClient: null,
    opencodeReviewActive: false, requireReview: true, localChecks: async () => [true, "stub"], resolveConflicts: async () => [true, "Resolved 1 conflict(s) and pushed"], ...o });
}
const merged = (gh: any) => gh.calls.some((c: any) => c[0] === "merge");
afterEach(() => { for (const k of ["REVIEW_WAIVE_AFTER_MINUTES", "REVIEW_WAIVE_MAX_LINES", "REVIEW_WAIVE_MAX_PER_RUN"]) delete process.env[k]; });

test("identity: App auth drops the owner from reviewers; git identity follows the bot login", () => {
  expect(reviewerLogins("juninmd")).toContain("juninmd");
  expect(reviewerLogins("juninmd", "renamed-bot[bot]", true)).toEqual(["renamed-bot[bot]", "juninmd-bot[bot]", "gh-assistance[bot]"]);
  expect(gitIdentity("juninmd-bot[bot]").email).toBe("juninmd-bot[bot]@users.noreply.github.com");
});
test("trust is an exact login match: a human named like a bot is not trusted", () => {
  expect(isTrustedAuthor("dependabot[bot]")).toBe(true);
  expect(isTrustedAuthor("dependabot")).toBe(false);
  expect(isTrustedAuthor("JUNINMD")).toBe(true);
});
test("owner commands: /hold blocks before anything else; /unhold releases; bot-written text never counts", async () => {
  const c = ownerCommands([owner("/hold", T0), owner("/unhold", T0 + 1), { user: { login: "juninmd", type: "User" }, body: "<!-- x -->\n/hold", created_at: iso(T0 + 2) }], "juninmd");
  expect(c.hold).toBe(false);
  const p = pr(), gh = fakeGh(p, { getIssueComments: async () => [owner("/hold")] }), r = results();
  await agent(gh).processPr(p, r);
  expect(r.skipped[0].reason).toBe("owner_hold"); expect(merged(gh)).toBe(false);
});
test("owner objection in plain words is a deterministic veto, even with no AI available", async () => {
  expect((await evaluateCommentsWithLlm(null, [owner("não mergeia ainda, falta teste")], () => true, "juninmd")).decision).toBe("blocked");
  expect((await evaluateCommentsWithLlm(null, [owner("valeu, ficou bom")], () => true, "juninmd")).decision).toBe("merge");
});
test("/merge after the newest commit merges without model review; before it, it does not", async () => {
  expect(mergeCommandValid(ownerCommands([owner("/merge", T0 - 1)], "juninmd"), T0)).toBe(false);
  const p = pr(), gh = fakeGh(p, { getIssueComments: async () => [owner("/merge", T0 + 60_000)] }), a = agent(gh), r = results();
  let reviewed = false; a.reviews.runOpencodeReview = async () => { reviewed = true; return "unreviewed"; };
  await a.processPr(p, r);
  expect(reviewed).toBe(false); expect(merged(gh)).toBe(true);
  const leaky = fakeGh(p, { getIssueComments: async () => [owner("/merge", T0 + 60_000)], getFiles: async () => [{ filename: ".env", status: "added", patch: "+A=1" }] }), r2 = results();
  await agent(leaky).processPr(p, r2);
  expect(merged(leaky)).toBe(false); expect(r2.blocked[0].reason).toStartWith("owner_merge_credential_found");
});
test("/review newer than the last bot review forces a fresh verdict", async () => {
  const p = pr(), a = agent(fakeGh(p));
  expect(a.reviewForced(ownerCommands([owner("/review", T0 + 5)], "juninmd"), [{ body: "<!-- opencode-review -->", created_at: iso(T0) }])).toBe(true);
  expect(a.reviewForced(ownerCommands([owner("/review", T0)], "juninmd"), [{ body: "<!-- opencode-review -->", created_at: iso(T0 + 5) }])).toBe(false);
});
test("approval follows the PR diff: a clean base update (new SHA, same +/- lines) keeps it; a changed line does not", async () => {
  const fp = fingerprintFiles(files);
  const body = buildReviewComment(mkVerdict({ verdict: "APPROVE", summary: "ok" }), "1111111111", fp);
  const comments = [{ user: { login: "juninmd-bot[bot]" }, body }];
  const rebased = [{ ...files[0], patch: "@@ -10,2 +10,2 @@\n other ctx\n-old\n+new" }];
  expect(fingerprintFiles(rebased)).toBe(fp);
  expect(await approvalFor(fakeGh(pr(), { getFiles: async () => rebased }), pr(), comments, reviewerLogins("juninmd"))).toBe("approved");
  expect(await approvalFor(fakeGh(pr(), { getFiles: async () => [{ ...files[0], patch: "-old\n+evil" }] }), pr(), comments, reviewerLogins("juninmd"))).toBe("missing");
  expect(approvalState(comments, SHA, reviewerLogins("juninmd"))).toBe("missing"); // SHA alone does not match
});
test("waiver tiers: pending notice, wait, then waive; large diffs and the run cap never waive", () => {
  const p = pr(), pending = [{ body: `${PENDING_MARKER}\nSHA \`${SHA.slice(0, 8)}\``, created_at: iso(T0) }];
  expect(decideWaiver(p, [], 0, T0)).toBe("pending");
  expect(decideWaiver(p, pending, 0, T0 + 10 * 60_000)).toBe("wait");
  expect(decideWaiver(p, pending, 0, T0 + 31 * 60_000)).toBe("waive");
  expect(decideWaiver(pr({ additions: 900 }), pending, 0, T0 + 31 * 60_000)).toBe("too_large");
  expect(decideWaiver(p, pending, 3, T0 + 31 * 60_000)).toBe("cap");
});
test("model outage: first run posts the pending notice and defers (no merge); infra errors defer without any notice", async () => {
  const posted: string[] = [], gh = fakeGh(pr(), { commentOnPr: async (_p: any, b: string) => { posted.push(b); } });
  const mk = (review: any) => new ReviewRunner({ gh, log: () => {}, forRepository: () => ({}) as any, active: true, budget: 5, waitSeconds: 0, reviewers: ["juninmd"], review });
  expect(await mk(async () => null).runOpencodeReview(pr(), [])).toBe("deferred");
  expect(posted[0]).toContain("Revisão automática indisponível");
  const infra = mk(async () => { throw new ReviewInfraError("clone failed"); });
  for (let i = 0; i < 4; i++) expect(await infra.runOpencodeReview(pr(), [])).toBe("deferred");
  expect(posted.length).toBe(1); // no waiver, no breaker trip from infra errors
});
test("dependency lane: advisory-only checks are not CI; billing-blocked + clean scan merges; odd files never", async () => {
  const dep = pr({ user: { login: "dependabot[bot]" } }), lock = [{ filename: "package-lock.json", status: "modified", patch: "+x" }, { filename: "package.json", status: "modified", patch: "+y" }];
  const advisoryOnly = { state: "success", success_checks: [{ context: "release-drafter" }], advisory_checks: ["release-drafter"], billing_checks: [] };
  expect(realPassedChecks(advisoryOnly)).toBe(0);
  expect((await laneAllowsMerge(fakeGh(dep, { getFiles: async () => lock }), dep, advisoryOnly)).reason).toBe("dependency_no_real_checks");
  const billing = { state: "success", success_checks: [{ context: "ci" }], billing_checks: ["ci"], advisory_checks: [] };
  expect((await laneAllowsMerge(fakeGh(dep, { getFiles: async () => lock }), dep, billing)).ok).toBe(true);
  const odd = await laneAllowsMerge(fakeGh(dep, { getFiles: async () => [...lock, { filename: "src/x.ts", status: "modified", patch: "+z" }] }), dep, billing);
  expect(odd.reason).toStartWith("dependency_lane_unexpected_files");
});
test("conflicts: dependabot gets '@dependabot rebase' (no push, once per 6h); others resolve inline; stale manual label is cleared", async () => {
  const dep = pr({ mergeable: false, user: { login: "dependabot[bot]" } }), gh = fakeGh(dep);
  let resolverCalled = false; const a = agent(gh, { resolveConflicts: async () => { resolverCalled = true; return [true, "x"]; } }), r = results();
  await a.processPr(dep, r);
  expect(gh.calls.filter((c: any) => c[0] === "comment").map((c: any) => c[1])).toEqual(["@dependabot rebase"]);
  expect(resolverCalled).toBe(false); expect(r.skipped[0].reason).toBe("dependabot_rebase_requested");
  const again = fakeGh(dep, { getIssueComments: async () => [{ body: "@dependabot rebase", created_at: iso(Date.now() - 60_000) }] });
  await agent(again).processPr(dep, results());
  expect(again.calls.some((c: any) => c[0] === "comment")).toBe(false);
  const mine = pr({ mergeable: false }), g2 = fakeGh(mine), r2 = results();
  await agent(g2).processPr(mine, r2);
  expect(r2.conflicts_resolved).toHaveLength(1); expect(merged(g2)).toBe(false); // new SHA: review + CI next cycle
  const clean = pr({ labels: [{ name: MANUAL_CONFLICT_LABEL }] }), g3 = fakeGh(clean);
  await agent(g3, { requireReview: false }).processPr(clean, results());
  expect(g3.calls).toContainEqual(["unlabel", MANUAL_CONFLICT_LABEL]);
});
test("PR lease: a fresh bot/busy label means busy; an old one is taken over", async () => {
  const busy = pr({ labels: [{ name: BUSY_LABEL }], updated_at: iso(Date.now() - 60_000) });
  expect(await acquirePrLock(fakeGh(busy), busy)).toBe(false);
  const stale = pr({ labels: [{ name: BUSY_LABEL }], updated_at: iso(Date.now() - 2 * 60 * 60_000) });
  expect(await acquirePrLock(fakeGh(stale), stale)).toBe(true);
});
test("billing scan: every file is scanned; a missing patch falls back to the file content; unreadable text blocks", async () => {
  const many = Array.from({ length: 150 }, (_, i) => ({ filename: `f${i}.txt`, status: "added", patch: "+ok" }));
  many.push({ filename: "f150.txt", status: "added", patch: "+-----BEGIN RSA PRIVATE KEY-----\n+MIIEowIBAAKCAQEA1234567890abcdef\n+-----END RSA PRIVATE KEY-----" });
  expect((await scanAddedLines(fakeGh(pr()), pr(), many)).some((h) => h.file === "f150.txt")).toBe(true);
  const big = [{ filename: "big.sql", status: "added", additions: 99999 }];
  const viaContents = fakeGh(pr(), { getContents: async () => ({ path: "big.sql", sha: "s", content: "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA1234567890abcdef\n-----END RSA PRIVATE KEY-----" }) });
  expect((await scanAddedLines(viaContents, pr(), big)).length).toBeGreaterThan(0);
  expect((await scanAddedLines(fakeGh(pr()), pr(), big))[0].rule_id).toBe("unscannable-file");
});
test("no CI: the bot's local build/test gate stands in; a red local gate blocks the merge", async () => {
  const p = pr(), gh = fakeGh(p, { getCheckRuns: async () => [], getIssueComments: async () => [{ user: { login: "juninmd" }, body: `<!-- opencode-review -->\n**Veredito:** \`APPROVE\`\n<sub>SHA \`${SHA.slice(0, 8)}\`</sub>` }] });
  const r = results();
  await agent(gh, { localChecks: async () => [false, "local_checks_failed: npm test failed"] }).tryMerge(p, r, []);
  expect(merged(gh)).toBe(false); expect(r.blocked[0].reason).toStartWith("local_checks_failed");
});
test("red pipeline is handled before the model review (no review slot spent)", async () => {
  const p = pr(), gh = fakeGh(p, { getCheckRuns: async () => [{ name: "ci", status: "completed", conclusion: "failure" }] }), a = agent(gh);
  let reviewed = false; a.reviews.runOpencodeReview = async () => { reviewed = true; return "approved"; };
  const r = results(); await a.processPr(p, r);
  expect(reviewed).toBe(false); expect(r.pipeline_failures).toHaveLength(1);
});
test("review fixes: '++'/'--' content lines change the fingerprint; pasted waiver markers by others are ignored", () => {
  const base = fingerprintFiles(files);
  expect(fingerprintFiles([{ ...files[0], patch: files[0].patch + "\n+++i; evil()" }])).not.toBe(base);
  expect(fingerprintFiles([{ ...files[0], patch: files[0].patch + "\n--- sql comment removed" }])).not.toBe(base);
  const forged = [{ user: { login: "rando" }, body: `<!-- pr-assistant:review-waived -->\nSHA \`${SHA.slice(0, 8)}\``, created_at: iso(T0) }];
  expect(decideWaiver(pr(), forged, 0, T0, reviewerLogins("juninmd"))).toBe("pending");
});
test("review fixes: /merge <sha> pins the head; a later /merge supersedes an earlier 'wip'; bot phrases posted as the owner are not the owner", async () => {
  expect(mergeCommandValid(ownerCommands([owner(`/merge ${SHA.slice(0, 7)}`, T0 - 99)], "juninmd"), null, SHA)).toBe(true);
  expect(mergeCommandValid(ownerCommands([owner("/merge 1234567", T0 + 99)], "juninmd"), T0, SHA)).toBe(false);
  expect((await evaluateCommentsWithLlm(null, [owner("wip", T0), owner("/merge", T0 + 1)], () => true, "juninmd")).decision).toBe("merge");
  const botAsOwner = owner("**Nao foi possivel resolver os conflitos de merge**\n\n...", T0 + 2);
  expect((await evaluateCommentsWithLlm(null, [owner("não mergeia", T0), botAsOwner], () => true, "juninmd")).decision).toBe("blocked");
});
test("review fixes: a waived PR is still scanned for credentials before merging", async () => {
  const p = pr(), gh = fakeGh(p, { getFiles: async () => [{ filename: ".env", status: "added", patch: "+A=1" }] }), a = agent(gh), r = results();
  a.reviews.runOpencodeReview = async () => "waived";
  await a.processPr(p, r);
  expect(merged(gh)).toBe(false); expect(r.blocked[0].reason).toStartWith("waived_credential_found");
});
