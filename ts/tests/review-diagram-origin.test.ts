import { expect, test } from "bun:test";
import { buildOriginMetadata } from "../src/agents/core/utils.ts";
import { buildReviewComment, cleanDiagram, mkVerdict } from "../src/agents/pr_assistant/review-verdict.ts";

test("merge notices carry no model line; AI output keeps it", () => {
  expect(buildOriginMetadata("pr_assistant", null)).not.toContain("Modelo");
  expect(buildOriginMetadata("pr_assistant", "x/y")).toContain("`x/y`");
});
test("review comment renders a valid mermaid block after the summary and drops invalid ones", () => {
  const body = buildReviewComment(mkVerdict({ verdict: "APPROVE", summary: "ok", diagram: "flowchart TD\n A-->B" }));
  expect(body.indexOf("**Resumo:**")).toBeLessThan(body.indexOf("```mermaid"));
  expect(body.indexOf("```mermaid")).toBeLessThan(body.indexOf("### 🔎 Achados"));
  expect(cleanDiagram("<script>x</script>")).toBeUndefined();
  expect(cleanDiagram("```mermaid\nsequenceDiagram\nA->>B: hi\n```")).toStartWith("sequenceDiagram");
  expect(buildReviewComment(mkVerdict({ verdict: "APPROVE", summary: "ok" }))).not.toContain("mermaid");
});
