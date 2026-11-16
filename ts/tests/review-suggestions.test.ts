import { afterEach, expect, test } from "bun:test";
import { inlineComments, parsePatch, prLines } from "../src/agents/pr_assistant/review-lines.ts";
import { rawLines, sourceFromFiles, suggestionBlock } from "../src/agents/pr_assistant/review-suggestions.ts";
import { groundFindings } from "../src/agents/pr_assistant/review-grounding.ts";
import { mkFinding, parseReview } from "../src/agents/pr_assistant/review-verdict.ts";

const saved = { ...process.env };
afterEach(() => { for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k]; Object.assign(process.env, saved); });

const PATCH = "@@ -10,3 +10,4 @@ function charge() {\n   const total = sum(items);\n-  return total / count;\n+    const avg = total / count;\n+\treturn avg;\n }";
const files = [{ filename: "src/pay.ts", patch: PATCH }, { filename: "logo.png" }];
const ORIGINAL = "    const avg = total / count;";
const f = (o: Record<string, unknown> = {}) => mkFinding({ file: "src/pay.ts", line: 11, severity: "error", issue: "count pode ser 0", evidence: "const avg = total / count;", suggestion: "const avg = count ? total / count : 0;", ...o });

test("rawLines keeps the indentation of added and context lines", () => {
  expect([...rawLines(PATCH)]).toEqual([[10, "  const total = sum(items);"], [11, ORIGINAL], [12, "\treturn avg;"], [13, "}"]]);
  expect(sourceFromFiles(files).get("logo.png")!.size).toBe(0);
});
test("a local fix becomes an Apply-suggestion block with the line's indentation restored", () => {
  expect(suggestionBlock(f(), ORIGINAL)).toBe("```suggestion\n    const avg = count ? total / count : 0;\n```");
  // already indented, fenced by the model, several lines, quote pasted with its diff marker
  expect(suggestionBlock(f({ evidence: "+    const avg = total / count;", suggestion: "```ts\n    if (!count) return 0;\n    const avg = total / count;\n```" }), ORIGINAL))
    .toBe("```suggestion\n    if (!count) return 0;\n    const avg = total / count;\n```");
  expect(suggestionBlock(f({ evidence: "return avg;", suggestion: "return Math.round(avg);" }), "\treturn avg;")).toBe("```suggestion\n\treturn Math.round(avg);\n```");
  // code containing a fence gets a longer one, so the block cannot be closed early
  expect(suggestionBlock(f({ suggestion: "const doc = '```';" }), ORIGINAL)).toBe("````suggestion\n    const doc = '```';\n````");
});
test("no suggestion when applying it could not be trusted", () => {
  expect(suggestionBlock(f({ suggestion: "" }), ORIGINAL)).toBe("");
  expect(suggestionBlock(f({ evidence: "" }), ORIGINAL)).toBe(""); // nothing ties the fix to this line
  expect(suggestionBlock(f({ evidence: "const total = sum(items);" }), ORIGINAL)).toBe(""); // quote is another line
  expect(suggestionBlock(f({ evidence: "const avg = total / count;\nreturn avg;" }), ORIGINAL)).toBe(""); // would replace only one of two lines
  expect(suggestionBlock(f({ suggestion: "const  avg = total / count;" }), ORIGINAL)).toBe(""); // no-op
  expect(suggestionBlock(f({ suggestion: Array(25).fill("x();").join("\n") }), ORIGINAL)).toBe("");
  expect(suggestionBlock(f({ suggestion: "<<<<<<< HEAD\na" }), ORIGINAL)).toBe("");
  expect(suggestionBlock(f(), undefined)).toBe("");
  process.env.REVIEW_SUGGESTIONS_ENABLED = "false";
  expect(suggestionBlock(f(), ORIGINAL)).toBe("");
});
test("inline comments carry the suggestion only with the source and only on visible lines", () => {
  const visible = new Map([["src/pay.ts", parsePatch(PATCH)]]), source = sourceFromFiles(files);
  const [c] = inlineComments([f(), f({ line: 99 })], visible, source);
  expect(c).toEqual({ path: "src/pay.ts", line: 11, side: "RIGHT", body: "🔴 **error** — count pode ser 0\n\n```suggestion\n    const avg = count ? total / count : 0;\n```" });
  expect(inlineComments([f()], visible)[0]!.body).toBe("🔴 **error** — count pode ser 0");
  expect(inlineComments([f({ suggestion: "" })], visible, source)[0]!.body).not.toContain("suggestion");
});
test("model answer → grounded line → suggestion on that exact line", async () => {
  const v = parseReview(JSON.stringify({ verdict: "REQUEST_CHANGES", summary: "s", findings: [{ file: "src/pay.ts", line: 40, severity: "error", evidence: "return avg;", issue: "sem arredondar", suggestion: "return Math.round(avg);" }] }))!;
  expect(v.findings[0]!.suggestion).toBe("return Math.round(avg);");
  const section = `diff --git a/src/pay.ts b/src/pay.ts\n--- a/src/pay.ts\n+++ b/src/pay.ts\n${PATCH}\n`;
  const grounded = groundFindings(v.findings, { "src/pay.ts": section }).findings;
  expect(grounded[0]!.line).toBe(12); // the model said 40; the quote is on 12
  const { visible, source } = await prLines({ getFiles: async () => files } as any, { number: 1, base: { repo: { full_name: "o/r" } } });
  expect(inlineComments(grounded, visible, source)[0]).toMatchObject({ line: 12, body: expect.stringContaining("```suggestion\n\treturn Math.round(avg);\n```") });
});
