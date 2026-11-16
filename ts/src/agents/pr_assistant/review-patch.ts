/** Deterministic auto-fix: ask the model for a unified diff and apply it with `git apply`. */
import * as git from "./review-git.ts";
import type { ReviewVerdict } from "./review-verdict.ts";

const PATCH_FENCE = /```(?:diff|patch)?\n([\s\S]*?)```/;
export function fixPrompt(v: ReviewVerdict): string {
  const findings = v.findings.map((f) => `- \`${f.file}\` (linha ${f.line || "?"}, ${f.severity}): ${f.issue}`).join("\n");
  return "Você é um engenheiro sênior. Gere um patch unificado no formato `git diff` que " +
    "corrija APENAS os problemas abaixo no repositório deste PR.\n" +
    "Regras: mudanças mínimas e seguras; não refatore código não relacionado; não altere " +
    "testes para mascarar falhas, corrija a causa.\n" +
    "Responda SOMENTE com o patch, começando por `diff --git` e sem cercas markdown.\n\n" +
    `Problemas:\n${findings}\n`;
}
export function extractPatch(text?: string | null): string {
  if (!text) return "";
  const body = PATCH_FENCE.exec(text)?.[1] ?? text;
  for (const marker of ["diff --git", "--- "]) { const i = body.indexOf(marker); if (i !== -1) return body.slice(i).trim() + "\n"; }
  return "";
}
export const applyPatch = (cloneDir: string, patch: string) => git.applyPatch(cloneDir, patch);
import * as ws from "./review-workspace.ts";
export async function requestPatch(cloneDir: string, v: ReviewVerdict, model: string): Promise<string> {
  const out = await ws.runOpencode(cloneDir, fixPrompt(v), model, ws.reviewTimeout());
  return out ? extractPatch(out) : "";
}
