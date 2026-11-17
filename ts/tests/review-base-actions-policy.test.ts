import { expect, test } from "bun:test";
import { instructions } from "../src/agents/pr_assistant/review-flow.ts";
import { verifyPrompt } from "../src/agents/pr_assistant/review-verify.ts";

const pr = { number: 1, title: "ci: use @main", head: { sha: "h".repeat(40) }, base: { ref: "main", sha: "b".repeat(40), repo: { full_name: "o/r" } } } as any;

test("reviewer treats juninmd/base-actions@main as the fleet policy, not a supply-chain defect", () => {
  const text = instructions(pr);
  expect(text).toContain("juninmd/base-actions");
  expect(text).toContain("@main");
  expect(text).toContain("NÃO é defeito");
});

test("reviewer still requires commit SHA pins for third-party actions", () => {
  expect(instructions(pr)).toContain("Actions de terceiros continuam exigindo SHA de commit");
});

test("verifier refutes claims that flag base-actions@main as a risk", () => {
  expect(verifyPrompt("t", [], {})).toContain("juninmd/base-actions/...@main");
});
