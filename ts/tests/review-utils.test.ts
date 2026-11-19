import { expect, test } from "bun:test";
import { parsePatch, parseDiff, validateFindings, inlineComments } from "../src/agents/pr_assistant/review-lines.ts";
import { splitByFile, buildPackages, rulesText, mergeVerdicts, fnmatch } from "../src/agents/pr_assistant/review-packages.ts";
import { hasEvidence, evidenceFinding } from "../src/agents/pr_assistant/pr-evidence.ts";
import { extractPatch } from "../src/agents/pr_assistant/review-patch.ts";
import { mkFinding, mkVerdict } from "../src/agents/pr_assistant/review-verdict.ts";

const diff = "diff --git a/a/x.py b/a/x.py\n--- a/a/x.py\n+++ b/a/x.py\n@@ -1,2 +1,3 @@\n a\n+b\n c\ndiff --git a/b.py b/b.py\n+++ b/b.py\n@@ -0,0 +1 @@\n+z\n";
test("parsePatch/parseDiff", () => {
  expect([...parsePatch("@@ -1,2 +5,3 @@\n a\n-x\n+b\n c")]).toEqual([5, 6, 7]);
  expect([...parseDiff(diff).get("a/x.py")!]).toEqual([1, 2, 3]);
});
test("validate drops bad lines and dupes", () => {
  const vis = parseDiff(diff);
  const fs = validateFindings([mkFinding({ file: "a/x.py", line: 2, issue: "Bad!" }), mkFinding({ file: "a/x.py", line: 99, issue: "Other" }), mkFinding({ file: "a/x.py", line: 2, issue: "bad" }), mkFinding({ issue: " " })], vis);
  expect(fs.map((f) => f.line)).toEqual([2, 0]);
  expect(inlineComments(fs, vis)).toHaveLength(1);
});
test("packages and rules", () => {
  const s = splitByFile(diff);
  expect(Object.keys(s)).toEqual(["a/x.py", "b.py"]);
  expect(buildPackages(s, 10_000)).toHaveLength(1);
  expect(buildPackages(s, 10)).toHaveLength(2);
  expect(fnmatch("a/x.py", "a/*.py")).toBe(true);
  expect(rulesText([{ path: "*.md", rule: "r" }], ["a.py"])).toBe("");
  expect(rulesText([{ path: "a/*", rule: "r" }], ["a/x.py"])).toContain("- `a/*`: r");
});
test("mergeVerdicts", () => {
  const m = mergeVerdicts([mkVerdict({ verdict: "APPROVE", summary: "ok" }), mkVerdict({ verdict: "REQUEST_CHANGES", summary: "no" })]);
  expect(m.verdict).toBe("REQUEST_CHANGES"); expect(m.summary).toBe("ok | no");
});
test("evidence", () => {
  expect(hasEvidence("![x](http://i/p.png)")).toBe(true);
  expect(hasEvidence("### Evidências\n<!-- x -->\n")).toBe(false);
  expect(hasEvidence("### Evidências\nSaída dos testes: 10 passed, 0 failed")).toBe(true);
  expect(evidenceFinding("nada")?.severity).toBe("warn");
});
test("hasEvidence accepts the fleet's 'Como foi verificado' section (agar#197, etanol-gasolina#102)", () => {
  expect(hasEvidence("## Como foi verificado\n- `pnpm test` → 47 passed")).toBe(true);
  expect(hasEvidence("### Verificação\n- `bun test` → 245 pass, 0 fail")).toBe(true);
  expect(hasEvidence("## Como foi verificado\n\n## Riscos\nnenhum")).toBe(false);
  expect(hasEvidence("## Verificações pendentes\nrodar depois do merge")).toBe(false);
});
test("extractPatch", () => {
  expect(extractPatch("blah\n```diff\ndiff --git a/x b/x\n+1\n```")).toBe("diff --git a/x b/x\n+1\n");
  expect(extractPatch("nope")).toBe("");
});
