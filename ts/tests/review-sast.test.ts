import { expect, test } from "bun:test";
import { mergeSast, promptBlock, toFindings } from "../src/agents/pr_assistant/review-sast.ts";
import { mkVerdict, APPROVE, REQUEST_CHANGES } from "../src/agents/pr_assistant/review-verdict.ts";

const added = new Map([["a.ts", new Set([3])]]);
test("secret on an added line blocks; others warn; old lines and duplicates are dropped", () => {
  const f = toFindings([
    { file: "a.ts", line: 3, rule_id: "gitleaks:generic-api-key" }, { file: "a.ts", line: 3, rule_id: "gitleaks:generic-api-key" },
    { file: "a.ts", line: 3, rule_id: "semgrep:x" }, { file: "a.ts", line: 9, rule_id: "gitleaks:old" }, { file: "b.ts", line: 3, rule_id: "semgrep:y" },
  ], added);
  expect(f.map((x) => x.severity)).toEqual(["error", "warn"]);
});
test("mergeSast turns an approval into REQUEST_CHANGES on a secret, keeps it on warn only", () => {
  const v = mkVerdict({ verdict: APPROVE, summary: "ok" });
  const [err] = toFindings([{ file: "a.ts", line: 3, rule_id: "trufflehog:AWS" }], added);
  expect(mergeSast(v, [err!])!.verdict).toBe(REQUEST_CHANGES);
  const [warn] = toFindings([{ file: "a.ts", line: 3, rule_id: "semgrep:x" }], added);
  expect(mergeSast(v, [warn!])!.verdict).toBe(APPROVE);
});
test("without a model verdict only a secret yields one", () => {
  const [warn] = toFindings([{ file: "a.ts", line: 3, rule_id: "semgrep:x" }], added);
  expect(mergeSast(null, [warn!])).toBeNull();
  const [err] = toFindings([{ file: "a.ts", line: 3, rule_id: "gitleaks:k" }], added);
  expect(mergeSast(null, [err!])!.verdict).toBe(REQUEST_CHANGES);
});
test("promptBlock hands opencode type, file and line of each finding, never the value; empty when none", () => {
  expect(promptBlock([])).toBe("");
  const f = toFindings([{ file: "a.ts", line: 3, rule_id: "gitleaks:generic-api-key" }], added);
  const b = promptBlock(f);
  expect(b).toContain("`a.ts` linha 3 (error)");
  expect(b).toContain("gitleaks:generic-api-key");
  expect(b).toContain("não os repita");
});
