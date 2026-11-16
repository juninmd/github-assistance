import { describe, expect, test } from "bun:test";
import { JulesTrackerAgent } from "../src/agents/jules_tracker/agent.ts";
import * as u from "../src/agents/jules_tracker/utils.ts";
import { RepositoryAllowlist } from "../src/config/allowlist.ts";
import { tmp } from "./helpers.ts";
import { join } from "node:path";
import { writeFileSync } from "node:fs";

describe("jules_tracker utils", () => {
  test("pending question: ignores answered, falls back to statusMessage", () => {
    const acts = [{ createTime: "1", agentMessaged: { agentMessage: "Q1?" } }, { createTime: "2", userMessaged: {} }, { createTime: "3", agentMessaged: { agentMessage: "Q2?" } }];
    expect(u.getPendingQuestion({}, acts)).toBe("Q2?");
    expect(u.getPendingQuestion({}, acts.slice(0, 2))).toBeNull();
    expect(u.getPendingQuestion({ state: "AWAITING_USER_FEEDBACK", statusMessage: " hi " }, [])).toBe("hi");
    expect(u.latestActivityIsUserReply(acts.slice(0, 2))).toBe(true);
  });
  test("ensureOpenPrRequest", () => {
    expect(u.ensureOpenPrRequest("go")).toBe("go\n\nAo finalizar, abra o pull request.");
    expect(u.ensureOpenPrRequest("open a PR")).toBe("open a PR");
    expect(u.ensureOpenPrRequest("")).toBe(u.OPEN_PR_INSTRUCTION);
  });
  test("plan pending / pending plan / repo name", () => {
    expect(u.isPlanPending([{ planGenerated: {} }])).toBe(true);
    expect(u.isPlanPending([{ planGenerated: {} }, { planApproved: {} }])).toBe(false);
    expect(u.getPendingPlan([{ createTime: "1", planGenerated: { planDescription: "do x" } }])).toBe("do x");
    expect(u.extractRepositoryName({ sourceContext: { source: "sources/github/me/r" } })).toBe("me/r");
  });
});

describe("jules_tracker agent", () => {
  test("answers question, approves plan, flags failures", async () => {
    const dir = tmp(), path = join(dir, "r.json"); writeFileSync(path, JSON.stringify({ repositories: ["me/r"], users: [] }));
    const sent: [string, string][] = [];
    const jules: any = {
      listSessions: async () => [
        { id: "a", state: "AWAITING_USER_FEEDBACK", sourceContext: { source: "sources/github/me/r" }, statusMessage: "which db?", url: "u" },
        { id: "b", state: "IN_PROGRESS", sourceContext: { source: "sources/github/me/r" } },
        { id: "c", state: "COMPLETED", sourceContext: { source: "sources/github/me/r" } }],
      listActivities: async (id: string) => (id === "b" ? [{ planGenerated: { planDescription: "plan" } }] : []),
      sendMessage: async (id: string, m: string) => { sent.push([id, m]); }, approvePlan: async (id: string) => { sent.push([id, "APPROVED"]); },
    };
    const gh: any = { getRepo: async () => ({}), getOpenIssues: async () => [] };
    const a = new JulesTrackerAgent({ githubClient: gh, julesClient: jules, allowlist: new RepositoryAllowlist(path), telegram: { sendMessage: async () => true } as any, aiClient: { generate: async (p: string) => (p.includes("reviewing") ? "APPROVE" : "use sqlite") } } as any);
    const r = await a.run();
    expect(r.answered_questions[0]).toMatchObject({ session_id: "a", answer: "use sqlite\n\nAo finalizar, abra o pull request." });
    expect(r.reviewed_plans[0]).toMatchObject({ session_id: "b", action: "approved" });
    expect(sent.map((s) => s[1])).toContain("APPROVED"); expect(r.status).toBeUndefined();
  });
  test("list failure → failed result", async () => {
    const a = new JulesTrackerAgent({ githubClient: {} as any, julesClient: { listSessions: async () => { throw new Error("x"); } } as any, allowlist: new RepositoryAllowlist("/nonexistent.json"), telegram: { sendMessage: async () => true } as any, aiClient: null } as any);
    expect((await a.run()).failed).toEqual([{ error: "Failed to list sessions" }]);
  });
});
