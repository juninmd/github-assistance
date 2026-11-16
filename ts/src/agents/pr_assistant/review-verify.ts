/** Adversarial verification: a second pass tries to refute each blocking finding against the real code before it can block a PR. */
import { extractJson, type Finding } from "./review-verdict.ts";
import { isPseudoFile, type Drop } from "./review-grounding.ts";
import { enabled } from "./review-flags.ts";

const ORDER: Record<string, number> = { nit: 0, info: 0, warn: 1, warning: 1, error: 2, critical: 2 };
const RADIUS = 15, MAX_EXCERPT_CHARS = 2500;
export type Check = { status: "confirmed" | "downgraded" | "refuted"; severity: string; reason: string };
export const verifyEnabled = () => enabled("REVIEW_VERIFY_ENABLED", true);
export const needsCheck = (f: Finding) => !isPseudoFile(f.file) && (ORDER[f.severity] ?? 0) >= 1;

/** Diff lines around `line` (new side), so the verifier judges the claim against the code and not against the claim's wording. */
export function excerpt(section: string, line: number): string {
  const rows: string[] = []; let cur = 0;
  for (const raw of (section || "").split(/\r?\n/)) {
    const m = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(raw);
    if (m) { cur = parseInt(m[1]!, 10); continue; }
    if (!cur || raw.startsWith("\\")) continue;
    if (!line || Math.abs(cur - line) <= RADIUS) rows.push(raw.startsWith("-") ? `     ${raw}` : `${String(cur).padStart(4)} ${raw}`);
    if (!raw.startsWith("-")) cur++;
  }
  return rows.join("\n").slice(0, MAX_EXCERPT_CHARS);
}
export function verifyPrompt(title: string, findings: Finding[], sections: Record<string, string>): string {
  const items = findings.map((f, i) =>
    `### Achado ${i + 1}\n- arquivo: ${f.file}${f.line ? `:${f.line}` : ""}\n- severidade: ${f.severity}\n- alegação: ${f.issue}\n` +
    `- trecho citado: ${f.evidence || "(nenhum)"}\nCódigo real (número da linha nova à esquerda):\n${excerpt(sections[f.file] ?? "", f.line) || "(trecho indisponível)"}`).join("\n\n");
  return "Você é um verificador cético de revisão de código. Outro revisor fez as alegações abaixo sobre um pull request. " +
    "Seu trabalho é tentar REFUTAR cada uma usando somente o código real mostrado (e o repositório, se disponível).\n" +
    "Marque `refuted` quando: o código não faz o que a alegação diz; é especulação sem cenário concreto de falha " +
    "(\"pode\", \"talvez\", \"verifique se\"); é estilo, ordem ou preferência; reclama de algo que não está no código; " +
    "ou trata upgrade de dependência como defeito sem apontar a quebra.\n" +
    "Marque `downgraded` quando o problema existe mas a severidade está exagerada (informe a severidade correta).\n" +
    "Marque `confirmed` somente quando você consegue descrever a entrada/estado que leva ao comportamento errado.\n\n" +
    "Responda com APENAS um objeto JSON, sem texto fora dele:\n" +
    '{"results":[{"id":1,"status":"confirmed|downgraded|refuted","severity":"error|warn|nit","reason":"uma frase"}]}\n\n' +
    `Título do PR: ${title}\n\n${items}\n`;
}
export function parseVerification(text: string | null | undefined): Map<number, Check> {
  const out = new Map<number, Check>();
  const d = text ? extractJson(text) : null;
  if (!d || !Array.isArray(d.results)) return out;
  for (const r of d.results) {
    const id = parseInt(r?.id, 10), status = String(r?.status ?? "").toLowerCase();
    if (Number.isNaN(id) || !["confirmed", "downgraded", "refuted"].includes(status)) continue;
    out.set(id, { status: status as Check["status"], severity: String(r.severity ?? "").toLowerCase(), reason: String(r.reason ?? "").trim() });
  }
  return out;
}
/** Refuted findings are dropped, downgraded ones lose severity (never gain); anything the verifier skipped stays as it was. */
export function applyVerification(findings: Finding[], checks: Map<number, Check>): { findings: Finding[]; dropped: Drop[] } {
  const kept: Finding[] = [], dropped: Drop[] = [];
  findings.forEach((f, i) => {
    const c = checks.get(i + 1);
    if (c?.status === "refuted") { dropped.push({ finding: f, reason: `refutado na verificação${c.reason ? `: ${c.reason}` : ""}` }); return; }
    const lower = c?.status === "downgraded" && c.severity in ORDER && ORDER[c.severity]! < (ORDER[f.severity] ?? 0);
    kept.push(lower ? { ...f, severity: c!.severity } : f);
  });
  return { findings: kept, dropped };
}
export type Ask = (prompt: string) => Promise<string | null>;
/** Verify the blocking findings with `ask`; an unavailable or unparsable verifier changes nothing (fail-closed for merges). */
export async function verifyFindings(title: string, findings: Finding[], sections: Record<string, string>, ask: Ask): Promise<{ findings: Finding[]; dropped: Drop[]; ran: boolean }> {
  const targets = findings.filter(needsCheck);
  if (!verifyEnabled() || !targets.length) return { findings, dropped: [], ran: false };
  let checks = new Map<number, Check>();
  try { checks = parseVerification(await ask(verifyPrompt(title, targets, sections))); } catch { /* verifier unavailable */ }
  if (!checks.size) return { findings, dropped: [], ran: false };
  const res = applyVerification(targets, checks);
  const gone = new Set(res.dropped.map((d) => d.finding));
  const byOld = new Map(targets.filter((t) => !gone.has(t)).map((t, i) => [t, res.findings[i]!]));
  return { findings: findings.filter((f) => !gone.has(f)).map((f) => byOld.get(f) ?? f), dropped: res.dropped, ran: true };
}
