import { expect, test } from "bun:test";
import { groundFindings } from "../src/agents/pr_assistant/review-grounding.ts";
import { blocks, mkFinding, mkVerdict } from "../src/agents/pr_assistant/review-verdict.ts";

// cc-litellm#43: the model quoted `abs >= 1e6`, a line the PR had already replaced with `abs >= PROMOTE_M`, and blocked the merge.
const SECTION = "diff --git a/src/fmt.ts b/src/fmt.ts\n--- a/src/fmt.ts\n+++ b/src/fmt.ts\n@@ -3,3 +3,3 @@ export function fmt(n: number) {\n   const abs = Math.abs(n);\n-  if (abs >= 1e6) return big(n);\n+  if (abs >= PROMOTE_M) return big(n);\n   return small(n);\n";
const sections = { "src/fmt.ts": SECTION };

test("a blocking finding that only quotes code the PR removed is capped at warn and cannot block", () => {
  const g = groundFindings([mkFinding({ file: "src/fmt.ts", line: 4, severity: "error", issue: "magic number 1e6", evidence: "if (abs >= 1e6) return big(n);" })], sections);
  expect(g.findings).toEqual([expect.objectContaining({ file: "src/fmt.ts", line: 0, severity: "warn" })]);
  expect(blocks(mkVerdict({ verdict: "REQUEST_CHANGES", summary: "", findings: g.findings }))).toBe(false);
});
test("a quote on an added line keeps its blocking severity", () => {
  const g = groundFindings([mkFinding({ file: "src/fmt.ts", severity: "critical", issue: "x", evidence: "if (abs >= PROMOTE_M) return big(n);" })], sections);
  expect(g.findings).toEqual([expect.objectContaining({ line: 4, severity: "critical" })]);
});
test("a non-blocking finding on removed code keeps its severity", () => {
  const g = groundFindings([mkFinding({ file: "src/fmt.ts", severity: "nit", issue: "x", evidence: "if (abs >= 1e6) return big(n);" })], sections);
  expect(g.findings[0]?.severity).toBe("nit");
});
