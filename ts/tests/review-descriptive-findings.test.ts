import { expect, test } from "bun:test";
import { instructions } from "../src/agents/pr_assistant/review-flow.ts";
import { verifyPrompt } from "../src/agents/pr_assistant/review-verify.ts";

// code-street#86: "Validação consistente no endpoint admin payout" came back as a blocking `error`.
const pr = { number: 86, title: "fix(api): valida amount", head: { sha: "h".repeat(40) }, base: { ref: "main", sha: "b".repeat(40), repo: { full_name: "o/r" } } } as any;

test("reviewer is told a finding is a defect, never a description or praise of the change", () => {
  expect(instructions(pr)).toContain("Achado é defeito, não resumo");
});

test("verifier refutes findings that only describe or praise the change", () => {
  expect(verifyPrompt("t", [], {})).toContain("apenas descreve ou elogia a mudança sem apontar defeito");
});
