import { afterEach, expect, test } from "bun:test";
import { SPECIALISTS, activeSpecialists, mergeFindings, reviewWithSubagents, subagentsEnabled, minDiffChars } from "../src/agents/pr_assistant/review-subagents.ts";

const saved = { ...process.env };
afterEach(() => { for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k]; Object.assign(process.env, saved); });
const pr = { title: "t", number: 1, head: { ref: "f", sha: "s" }, base: { ref: "main" } } as any;
const gh = { getFileContent: async () => null, getReadme: async () => null } as any;

test("subagents: off by default, min chars default", () => {
  delete process.env.LLM_REVIEW_SUBAGENTS; expect(subagentsEnabled()).toBe(false);
  delete process.env.LLM_REVIEW_SUBAGENTS_MIN_CHARS; expect(minDiffChars()).toBe(1500);
  process.env.LLM_REVIEW_SUBAGENTS_MIN_CHARS = "50"; expect(minDiffChars()).toBe(50);
});
test("merge drops empty and dedupes across specialists", () => {
  const out = mergeFindings({ "Segurança": "- a.py: SQL injection in query", "Correção": "- a.py: sql injection in query!\n- b.py: off by one", "Testes": "No issues found." });
  expect(out.split("injection").length - 1).toBe(1); expect(out).toContain("off by one"); expect(out).not.toContain("Testes");
});
test("all clean → empty report", () => { expect(mergeFindings(Object.fromEntries(Object.keys(SPECIALISTS).map((n) => [n, "No issues found."])))).toBe(""); });
test("runs specialists with distinct focus and dedupes", async () => {
  process.env.REVIEW_ADVISORIES_ENABLED = "false";
  const prompts: string[] = [];
  const [ok, report] = await reviewWithSubagents(gh, pr, "diff", { generate: async (p) => { prompts.push(p); return "- x.py: bug"; } });
  expect(ok).toBe(true); expect(prompts.length).toBe(Object.keys(activeSpecialists()).length); expect(new Set(prompts).size).toBe(prompts.length);
  expect(report.split("x.py: bug").length - 1).toBe(1);
});
test("one failing specialist does not sink the review; all failing reports failure", async () => {
  let i = 0;
  const [ok, report] = await reviewWithSubagents(gh, pr, "d", { generate: async () => { const n = i++; if (n === 0) throw new Error("boom"); return n === 1 ? "- y.py: leak" : "No issues found."; } });
  expect(ok).toBe(true); expect(report).toContain("y.py: leak");
  const [ok2] = await reviewWithSubagents(gh, pr, "d", { generate: async () => { throw new Error("boom"); } });
  expect(ok2).toBe(false);
});
