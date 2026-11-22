import { expect, test } from "bun:test";
import { join } from "node:path";
import { writeFileSync } from "node:fs";
import { APPROVAL_LABEL, ApprovalGate, approvalId, TelegramApprovals } from "../src/agents/secret_remover/approval.ts";
import { FindingProcessor } from "../src/agents/secret_remover/processor.ts";
import { PRAssistantAgent } from "../src/agents/pr_assistant/agent.ts";
import { KEEP_DRAFT_LABEL } from "../src/agents/core/pr-options.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { tmp } from "./helpers.ts";

const F1 = { rule_id: "aws-key", file: "a.env", line: 3, commit: "c1" }, F2 = { rule_id: "gh-pat", file: "b.ts", line: 9, commit: "c2" };
const ID = approvalId("me/r", [F1, F2]);
const issue = (id: string, n = 5) => ({ number: n, html_url: `https://github.com/me/r/issues/${n}`, labels: [{ name: APPROVAL_LABEL }], body: `<!-- secret-guard:${id} -->\nx` });
const comment = (login: string, body: string, type = "User") => ({ user: { login, type }, body });
function gh(o: { issues?: any[]; comments?: any[] } = {}) {
  const calls: any[] = [];
  return { calls, getOpenIssues: async () => o.issues ?? [], getIssueComments: async () => o.comments ?? [],
    createIssue: async (_r: string, p: any) => { calls.push(["issue", p]); return { number: 9, html_url: "https://github.com/me/r/issues/9" }; },
    post: async (path: string, b: any) => { calls.push(["post", path, b.body]); return {}; }, patch: async (path: string, b: any) => { calls.push(["patch", path, b.state]); return {}; } } as any;
}
const tg = () => { const sent: any[] = []; return { sent, sendMessage: async (t: string, _m: string, k?: any) => { sent.push([t, k]); return true; } } as any; };

test("approval id is bound to the exact finding set, not to its order", () => {
  expect(approvalId("me/r", [F2, F1])).toBe(ID);
  expect(approvalId("me/r", [F1])).not.toBe(ID);
  expect(approvalId("me/other", [F1, F2])).not.toBe(ID);
  expect(ID).toMatch(/^[0-9a-f]{10}$/);
});

test("gate: only the owner's /aprovar (or a bot-persisted Telegram approval) approves", async () => {
  const check = (comments: any[], tgApproved = new Set<string>()) => new ApprovalGate(gh({ issues: [issue(ID)], comments }), tg(), "Me", tgApproved, () => {}).check("me/r", ID);
  expect(await check([comment("me", "/aprovar")])).toEqual({ approved: true, via: "github", issue: 5 });
  expect((await check([comment("intruder", "/aprovar")])).approved).toBe(false);
  expect((await check([comment("me", "pode /aprovar depois")])).approved).toBe(false); // must be the command, not a mention
  expect((await check([comment("me", `<!-- secret-guard:approved-telegram:${ID} -->`)])).approved).toBe(false); // a human cannot forge the bot marker
  expect(await check([comment("juninmd-bot[bot]", `<!-- secret-guard:approved-telegram:${ID} -->`, "Bot")])).toEqual({ approved: true, via: "telegram", issue: 5 });
  // An approval for another finding set never carries over.
  const other = await new ApprovalGate(gh({ issues: [issue("ffffffffff")], comments: [comment("me", "/aprovar")] }), tg(), "me", new Set(), () => {}).check("me/r", ID);
  expect(other.approved).toBe(false);
  // Fail-closed on API errors.
  const broken: any = { getOpenIssues: async () => { throw new Error("502"); } };
  expect((await new ApprovalGate(broken, tg(), "me", new Set(), () => {}).check("me/r", ID)).approved).toBe(false);
});

test("gate: a Telegram approval is persisted on the issue so the next run still sees it", async () => {
  const g = gh({ issues: [issue(ID)] });
  const r = await new ApprovalGate(g, tg(), "me", new Set([ID]), () => {}).check("me/r", ID);
  expect(r).toEqual({ approved: true, via: "telegram", issue: 5 });
  expect(g.calls[0][2]).toContain(`secret-guard:approved-telegram:${ID}`);
});

test("gate.request: one issue + one Telegram button per finding set; older requests are superseded", async () => {
  const g = gh({ issues: [issue("0123456789", 4)] }), t = tg();
  const r = await new ApprovalGate(g, t, "me", new Set(), () => {}).request("me/r", ID, [F1, F2]);
  expect(r).toEqual({ issue: 9, created: true });
  const created = g.calls.find((c: any) => c[0] === "issue")[1];
  expect(created.labels).toEqual([APPROVAL_LABEL]); expect(created.body).toContain(`secret-guard:${ID}`); expect(created.body).toContain("/aprovar");
  expect(created.body).not.toContain("redacted"); // no secret content, only locations
  expect(g.calls.some((c: any) => c[0] === "patch" && c[1].endsWith("/issues/4"))).toBe(true);
  expect(t.sent[0][1].inline_keyboard[0][0].callback_data).toBe(`sg:${ID}`);
  const again = gh({ issues: [issue(ID)] }), t2 = tg();
  expect(await new ApprovalGate(again, t2, "me", new Set(), () => {}).request("me/r", ID, [F1, F2])).toEqual({ issue: 5, created: false });
  expect(t2.sent).toHaveLength(0); expect(again.calls).toHaveLength(0);
});

test("processor: without approval nothing is rewritten; with approval it rewrites and closes the issue", async () => {
  const removed: string[] = [], notes: string[] = [];
  const mkProc = (approved: boolean, gateCalls: string[]) => new FindingProcessor({} as any, tg(), {} as any, () => {}, {
    check: async () => ({ approved, via: approved ? "github" : null, issue: approved ? 5 : null }),
    request: async () => { gateCalls.push("request"); return { issue: 9, created: true }; },
    close: async () => { gateCalls.push("close"); },
  } as any, async (_r: string, f: any) => { removed.push(f.file); return true; });
  const items = [{ f: F1, originalLine: "x" }, { f: F2, originalLine: "y" }], notify = async (_f: any, a: string) => { notes.push(a); };
  const g1: string[] = [], acts1: any[] = [];
  expect(await mkProc(false, g1).resolveRemovals("me/r", items, "/clone", "tok", notify, acts1)).toEqual({ removed: 0, awaiting: 2 });
  expect(removed).toEqual([]); expect(g1).toEqual(["request"]); expect(acts1.map((a) => a.status)).toEqual(["AWAITING_APPROVAL", "AWAITING_APPROVAL"]);
  expect(notes).toEqual(["AWAITING_APPROVAL", "AWAITING_APPROVAL"]);
  const g2: string[] = [], acts2: any[] = [];
  expect(await mkProc(true, g2).resolveRemovals("me/r", items, "/clone", "tok", notify, acts2)).toEqual({ removed: 2, awaiting: 0 });
  expect(removed).toEqual(["a.env", "b.ts"]); expect(g2).toEqual(["close"]); expect(acts2[0].approved_via).toBe("github");
  // No gate wired: never rewrite.
  const bare = new FindingProcessor({} as any, tg(), {} as any, () => {}, null, async () => { throw new Error("must not rewrite"); });
  expect((await bare.resolveRemovals("me/r", items, "/c", "t", notify, [])).awaiting).toBe(2);
});

test("telegram approvals: owner's private chat or listed ids only; updates acknowledged; errors approve nothing", async () => {
  const cq = (id: number, data: string, chat: any, from = 1) => ({ update_id: id, callback_query: { id: `q${id}`, data, from: { id: from }, message: { chat } } });
  const calls: any[] = [];
  const fetchFn: any = async (url: string, init: any) => {
    const body = JSON.parse(init.body); calls.push([url.split("/").pop(), body]);
    if (url.endsWith("getUpdates") && body.offset === undefined)
      return { json: async () => ({ ok: true, result: [cq(10, `sg:${ID}`, { id: 42, type: "private" }), cq(11, "sg:aaaaaaaaaa", { id: -5, type: "group" }), cq(12, "other", { id: 42, type: "private" })] }) };
    return { json: async () => ({ ok: true, result: [] }) };
  };
  const ids = await new TelegramApprovals("tok", "42", [], () => {}, fetchFn).poll();
  expect([...ids]).toEqual([ID]);
  expect(calls.filter((c) => c[0] === "answerCallbackQuery").map((c) => c[1].text.startsWith("Aprovado"))).toEqual([true, false]);
  expect(calls.at(-1)).toEqual(["getUpdates", { offset: 13, timeout: 0, limit: 1, allowed_updates: ["callback_query"] }]);
  const listed = await new TelegramApprovals("tok", "42", ["7"], () => {}, fetchFn).poll();
  expect(listed.size).toBe(0); // approver list set: chat membership alone is not enough
  const down: any = async () => { throw new Error("offline"); };
  expect((await new TelegramApprovals("tok", "42", [], () => {}, down).poll()).size).toBe(0);
  expect((await new TelegramApprovals(null, "42", [], () => {}, fetchFn).poll()).size).toBe(0);
});

test("pr-assistant: keep-draft PRs are reviewed but never merged, not even on owner /merge", async () => {
  const SHA = "abcdef0123456789abcdef0123456789abcdef01", calls: any[] = [];
  const p: any = { number: 7, title: "t", html_url: "u", mergeable: true, mergeable_state: "clean", created_at: "2020-01-01T00:00:00Z", user: { login: "juninmd" }, draft: true,
    labels: [{ name: KEEP_DRAFT_LABEL }], head: { sha: SHA, ref: "f", repo: { full_name: "o/r" } }, base: { ref: "main", repo: { full_name: "o/r" } } };
  const gh: any = { getIssueComments: async () => [{ user: { login: "juninmd", type: "User" }, body: "/merge", created_at: "2026-11-20T10:00:00Z" }],
    getCombinedStatus: async () => ({ statuses: [] }), getCheckRuns: async () => [], getPull: async () => p, addAssigneeToPr: async () => [true, ""], requestReviewerOnPr: async () => [true, ""],
    mergePr: async () => { calls.push("merge"); return [true, "ok"]; }, setDraft: async () => { calls.push("ready"); } };
  const pol = join(tmp(), "a.json"); writeFileSync(pol, JSON.stringify({ defaults: { mode: "merge", merge: true } }));
  const a: any = new PRAssistantAgent({ githubClient: gh, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram: tg(), autonomyPolicyPath: pol, aiClient: null, opencodeReviewActive: false, requireReview: true });
  let reviewed = 0; a.reviews.runOpencodeReview = async () => { reviewed++; return "approved"; };
  const r = { merged: [], conflicts_resolved: [], pipeline_failures: [], skipped: [] as any[], blocked: [] };
  await a.processPr(p, r);
  expect(reviewed).toBe(1); expect(r.skipped[0].reason).toBe("keep_draft"); expect(calls).toEqual([]);
});
