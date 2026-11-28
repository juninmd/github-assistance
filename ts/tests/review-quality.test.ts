import { expect, test } from "bun:test";
import { deletedFilesBlock, instructions, prDescriptionBlock } from "../src/agents/pr_assistant/review-prompt.ts";
import { refine } from "../src/agents/pr_assistant/review-refine.ts";
import { cleanDiagram, mkFinding, mkVerdict, REQUEST_CHANGES } from "../src/agents/pr_assistant/review-verdict.ts";
import { fileContext, verifyFindings, verifyPrompt } from "../src/agents/pr_assistant/review-verify.ts";

const basePr = {
  number: 259,
  title: "feat(web): add projects from the workspace",
  body: "<!-- template comment -->\nAdiciona projetos do workspace e corrige fluxo de sessão.\n\n### Evidências\nTestes OK",
  head: { sha: "a".repeat(40) },
  base: { ref: "main", sha: "b".repeat(40), repo: { full_name: "o/r" } },
} as any;

test("prompt: focuses on regressions, unified-diff semantics, severity calibration, pt-BR and includes sanitized PR body", () => {
  const full = instructions(basePr);
  expect(full).toContain("Regressões e quebra de contrato");
  expect(full).toContain("linhas com `-` são código REMOVIDO");
  expect(full).toContain("Não invente erro de compilação");
  expect(full).toContain("REQUEST_CHANGES` SOMENTE quando houver ao menos um achado `error`");
  expect(full).toContain("obrigatoriamente em português (pt-BR)");
  expect(full).toContain("Nunca desenhe o processo de revisão");
  expect(full).toContain("Adiciona projetos do workspace");
  expect(full).not.toContain("template comment");
  expect(full).toContain("leia o repositório no diretório atual");

  const diffOnly = instructions(basePr, { diffOnly: true });
  expect(diffOnly).toContain("modo somente-diff");
  expect(diffOnly).not.toContain("leia o repositório no diretório atual");
});

test("prDescriptionBlock: strips HTML comments, caps length, and omits empty bodies", () => {
  expect(prDescriptionBlock({ ...basePr, body: "<!-- only comment -->" })).toBe("");
  const huge = prDescriptionBlock({ ...basePr, body: "x".repeat(3000) });
  expect(huge).toContain("dado não confiável");
  expect(huge.length).toBeLessThan(1700);
});

test("deletedFilesBlock: lists removed files for regression checks and ignores lockfiles/binaries", () => {
  expect(deletedFilesBlock([{ path: "bun.lock", reason: "lockfile" }, { path: "a.png", reason: "binário" }])).toBe("");
  const block = deletedFilesBlock([
    { path: "src/old-island.tsx", reason: "removido" },
    { path: "bun.lock", reason: "lockfile" },
    { path: "src/legacy.css", reason: "removido" },
  ]);
  expect(block).toContain("Arquivos removidos neste PR");
  expect(block).toContain("src/old-island.tsx, src/legacy.css");
  expect(block).not.toContain("bun.lock");
});

test("verifier: fileContext exposes top imports plus surrounding lines around a distant finding", () => {
  const lines = [
    "import { useCallback, useState } from 'react';",
    ...Array.from({ length: 55 }, (_, i) => `const line${i + 2} = ${i + 2};`),
    "const handler = useCallback(() => setOpen(true), []);",
    "return handler;",
  ];
  const ctx = fileContext(lines.join("\n"), 57);
  expect(ctx).toContain("   1 import { useCallback, useState } from 'react';");
  expect(ctx).toContain("  ...");
  expect(ctx).toContain("  57 const handler = useCallback(() => setOpen(true), []);");
  expect(fileContext(null, 10)).toBe("");
});

test("verifier: prompt includes real file context from readFile and explicit diff/compile refutation rules", () => {
  const section = "diff --git a/src/Remote.tsx b/src/Remote.tsx\n--- a/src/Remote.tsx\n+++ b/src/Remote.tsx\n@@ -55,2 +55,3 @@\n const a = 1;\n+const handler = useCallback(() => {}, []);\n return handler;\n";
  const realFile = ["import { useCallback } from 'react';", ...Array.from({ length: 54 }, () => "// pad"), "const a = 1;", "const handler = useCallback(() => {}, []);", "return handler;"].join("\n");
  const f = mkFinding({ file: "src/Remote.tsx", line: 56, severity: "error", issue: "useCallback não está definida", evidence: "const handler = useCallback(() => {}, []);" });
  const prompt = verifyPrompt("feat", [f], { "src/Remote.tsx": section }, (p) => (p === "src/Remote.tsx" ? realFile : null));
  expect(prompt).toContain("Arquivo real no PR (cabeçalho/imports + entorno da linha):");
  expect(prompt).toContain("   1 import { useCallback } from 'react';");
  expect(prompt).toContain("linhas `-` (REMOVIDAS no diff)");
  expect(prompt).toContain("variável/símbolo indefinido, import ausente");
});

test("refine: forwards readFile to verifier so import/scope false positives can be refuted against the real file", async () => {
  const section = "diff --git a/src/Remote.tsx b/src/Remote.tsx\n--- a/src/Remote.tsx\n+++ b/src/Remote.tsx\n@@ -55,2 +55,3 @@\n const a = 1;\n+const handler = useCallback(() => {}, []);\n return handler;\n";
  const realFile = ["import { useCallback } from 'react';", ...Array.from({ length: 54 }, () => "// pad"), "const a = 1;", "const handler = useCallback(() => {}, []);", "return handler;"].join("\n");
  const v = mkVerdict({
    verdict: REQUEST_CHANGES,
    summary: "erro de compilação",
    findings: [mkFinding({ file: "src/Remote.tsx", line: 56, severity: "error", issue: "useCallback não está definida", evidence: "const handler = useCallback(() => {}, []);" })],
  });
  let sawImport = false;
  const out = await refine(basePr, v, { "src/Remote.tsx": section }, (p) => (p === "src/Remote.tsx" ? realFile : null), async (prompt) => {
    sawImport = prompt.includes("import { useCallback } from 'react';");
    return '{"results":[{"id":1,"status":"refuted","reason":"useCallback está importado na linha 1"}]}';
  });
  expect(sawImport).toBe(true);
  expect(out.verdict).toBe("APPROVE");
  expect(out.findings).toEqual([]);
});

test("verifyFindings: forwards readFile directly when called standalone", async () => {
  const section = "diff --git a/src/a.ts b/src/a.ts\n@@ -1 +1,2 @@\n const x = 1;\n+const y = x + 1;\n";
  const f = mkFinding({ file: "src/a.ts", line: 2, severity: "error", issue: "x indefinido", evidence: "const y = x + 1;" });
  let captured = "";
  await verifyFindings("t", [f], { "src/a.ts": section }, async (p) => { captured = p; return '{"results":[{"id":1,"status":"refuted","reason":"x na linha 1"}]}'; }, () => "const x = 1;\nconst y = x + 1;\n");
  expect(captured).toContain("Arquivo real no PR");
  expect(captured).toContain("   1 const x = 1;");
});

test("cleanDiagram: drops meta-review diagrams while keeping genuine architecture diagrams", () => {
  // Real production examples from sonido#8 and canto-widget#319
  const metaSonido = "flowchart TD\n    A[PR Recebido] --> B{Skill Match?};\n    B -- Sim --> C[code-review];\n    C --> J[Verdito Final (APPROVE/REQUEST_CHANGES)];";
  const metaCanto = "flowchart LR; A[Code Review] --> B[Assinatura incorreta];";
  const validCode = "flowchart LR\n  Client[Web UI] --> API[/api/sessions]\n  API --> Store[(SQLite)]";
  expect(cleanDiagram(metaSonido)).toBeUndefined();
  expect(cleanDiagram(metaCanto)).toBeUndefined();
  expect(cleanDiagram(validCode)).toBe(validCode);
});
