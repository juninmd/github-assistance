import { expect, test } from "bun:test";
import { groundFindings } from "../src/agents/pr_assistant/review-grounding.ts";
import { mergeVerdicts } from "../src/agents/pr_assistant/review-packages.ts";
import { mkFinding, mkVerdict } from "../src/agents/pr_assistant/review-verdict.ts";

// Big PRs are reviewed in packages and each package sees the other files as context, so the same claim comes back twice
// (with model line numbers that differ) and the PR comment lists it twice.
const SECTION = "diff --git a/src/pay.ts b/src/pay.ts\n--- a/src/pay.ts\n+++ b/src/pay.ts\n@@ -10,3 +10,4 @@ export function charge() {\n   const total = sum(items);\n+  const avg = total / count;\n+  return avg.toFixed(2);\n }\n";
const sections = { "src/pay.ts": SECTION };
const quote = "const avg = total / count;";

test("the same claim from two review packages is reported once, at its highest severity", () => {
  const merged = mergeVerdicts([
    mkVerdict({ verdict: "APPROVE", summary: "a", findings: [mkFinding({ file: "src/pay.ts", line: 3, severity: "warn", issue: "count pode ser 0", evidence: quote })] }),
    mkVerdict({ verdict: "REQUEST_CHANGES", summary: "b", findings: [mkFinding({ file: "b/src/pay.ts", line: 90, severity: "error", issue: "divisão por zero quando count=0", evidence: `+  ${quote}` })] }),
  ]);
  const g = groundFindings(merged.findings, sections);
  expect(g.findings).toEqual([expect.objectContaining({ file: "src/pay.ts", line: 11, severity: "error", issue: "divisão por zero quando count=0" })]);
  expect(g.dropped).toEqual([]);
});
test("different quotes, files or unquoted issues are kept apart", () => {
  const g = groundFindings([
    mkFinding({ file: "src/pay.ts", severity: "warn", issue: "x", evidence: quote }),
    mkFinding({ file: "src/pay.ts", severity: "warn", issue: "y", evidence: "return avg.toFixed(2);" }),
    mkFinding({ file: "src/pay.ts", line: 11, severity: "nit", issue: "nome ruim" }),
    mkFinding({ file: "src/pay.ts", line: 11, severity: "nit", issue: "falta teste" }),
    mkFinding({ file: "(descrição do PR)", severity: "warn", issue: "sem evidências" }),
    mkFinding({ file: "(descrição do PR)", severity: "warn", issue: "Sem evidências " }),
  ], sections);
  expect(g.findings.map((f) => f.issue)).toEqual(["x", "y", "nome ruim", "falta teste", "sem evidências"]);
});
