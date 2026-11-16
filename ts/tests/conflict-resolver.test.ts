import { expect, test } from "bun:test";
import { ConflictResolverAgent } from "../src/agents/conflict_resolver/agent.ts";
import { sendSummaryNotice } from "../src/agents/conflict_resolver/notifications.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";

const pr = (o: any = {}) => ({ number: 3, title: "t", html_url: "u", mergeable: false, labels: [], user: { login: "juninmd" }, head: { sha: "a", ref: "f", repo: { full_name: "o/r" } }, base: { ref: "main", repo: { full_name: "o/r" } }, ...o });
const mk = (gh: any = {}) => {
  const sent: string[] = [];
  const a = new ConflictResolverAgent({ githubClient: gh, julesClient: {} as any, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram: { sendMessage: async (t: string) => { sent.push(t); return true; } } as any });
  return { a, sent };
};
const res = () => ({ resolved: [], manual: [], pipeline_fixed: [], pipeline_manual: [], timestamp: "" }) as any;

test("trusted authors fall back to defaults; untrusted ignored", async () => {
  const { a } = mk();
  expect(a.isTrustedAuthor("renovate[bot]")).toBe(true);
  expect(a.isTrustedAuthor("rando")).toBe(false);
  const r = res(); await a.handlePr(pr({ user: { login: "rando" } }) as any, r);
  expect(r.manual).toHaveLength(0);
});
test("already-flagged PR is skipped", async () => {
  const { a } = mk(); const r = res();
  await a.handlePr(pr({ labels: [{ name: "needs-manual-conflict-resolution" }] }) as any, r);
  expect(r.resolved.length + r.manual.length).toBe(0);
});
test("summary lists counts and links", async () => {
  const sent: string[] = [];
  await sendSummaryNotice({ sendMessage: async (t: string) => { sent.push(t); return true; } } as any, [{ repo: "o/r", pr: 1, msg: "ok" }], [{ repo: "o/r", pr: 2, error: "<x>" }]);
  expect(sent[0]).toContain("Resolvidos:</b> <code>1"); expect(sent[0]).toContain("&lt;x&gt;"); expect(sent[0]).toContain("o/r/pull/2");
});
test("run with search failure still returns results", async () => {
  const { a } = mk({ searchPrs: async () => { throw new Error("boom"); }, getRateLimit: async () => ({ remaining: 5000 }) });
  a.checkRateLimit = async () => 5000;
  const r = await a.run();
  expect(r.resolved).toEqual([]);
});
