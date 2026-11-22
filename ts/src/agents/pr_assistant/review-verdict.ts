/** Structured code-review verdict: parse the model JSON and render the PR comment (advisory; not read by merge policy). */
import { buildOriginMetadata } from "../core/utils.ts";

export const REVIEW_MARKER = "<!-- opencode-review -->";
export const APPROVE = "APPROVE", REQUEST_CHANGES = "REQUEST_CHANGES";
export const LABEL_APPROVED = "review/approved", LABEL_CHANGES = "review/needs-changes", LABEL_CRITICAL = "review/critical";
export const GATE_NAME = "github-assistance/review";
export const LABEL_COLORS: Record<string, string> = { [LABEL_APPROVED]: "0e8a16", [LABEL_CHANGES]: "d93f0b", [LABEL_CRITICAL]: "b60205" };

const APPROVE_WORDS = new Set(["APPROVE", "APPROVED", "LGTM", "PASS"]);
const CHANGES_WORDS = new Set(["REQUEST_CHANGES", "CHANGES_REQUESTED", "REJECT", "REJECTED", "BLOCK"]);
const ICON: Record<string, string> = { error: "🔴", warn: "🟠", warning: "🟠", nit: "🟡", info: "🔵" };
const ORDER: Record<string, number> = { nit: 0, info: 0, warn: 1, warning: 1, error: 2, critical: 2 };

/** `evidence` is the code line the model quoted as proof; grounding checks it against the real diff. `suggestion` is the code that replaces that line. */
export type Finding = { file: string; line: number; severity: string; issue: string; evidence?: string; suggestion?: string };
export type ReviewVerdict = {
  verdict: string; summary: string; findings: Finding[]; model: string; fixed: boolean; commit: string;
  harness: string; skills_used: string[]; skills_checked: boolean;
};
export const mkFinding = (o: Partial<Finding> = {}): Finding => ({ file: "", line: 0, severity: "nit", issue: "", ...o });
export const mkVerdict = (o: Partial<ReviewVerdict> & { verdict: string; summary: string }): ReviewVerdict =>
  ({ findings: [], model: "", fixed: false, commit: "", harness: "", skills_used: [], skills_checked: false, ...o });

export const isApproved = (v: ReviewVerdict) => v.verdict === APPROVE;
export const isCritical = (v: ReviewVerdict) => v.findings.some((f) => (f.severity || "").toLowerCase() === "error");
/** True when any finding reaches `minSeverity` (nit < warn < error). */
export const blocks = (v: ReviewVerdict, minSeverity = "error") => {
  const threshold = ORDER[(minSeverity || "error").toLowerCase()] ?? 2;
  return v.findings.some((f) => (ORDER[(f.severity || "nit").toLowerCase()] ?? 0) >= threshold);
};
export const verdictLabel = (v: ReviewVerdict) => (isApproved(v) ? LABEL_APPROVED : LABEL_CHANGES);

/** First JSON object found in a model answer (mirrors Python raw_decode scan). */
export function extractJson(text: string): Record<string, any> | null {
  for (let i = text.indexOf("{"); i !== -1; i = text.indexOf("{", i + 1)) {
    let depth = 0, inStr = false, esc = false;
    for (let j = i; j < text.length; j++) {
      const c = text[j];
      if (inStr) { if (esc) esc = false; else if (c === "\\") esc = true; else if (c === '"') inStr = false; continue; }
      if (c === '"') inStr = true; else if (c === "{") depth++; else if (c === "}" && --depth === 0) {
        try { const d = JSON.parse(text.slice(i, j + 1)); if (d && typeof d === "object" && !Array.isArray(d)) return d; } catch { /* try next brace */ }
        break;
      }
    }
  }
  return null;
}
const normalizeVerdict = (v: unknown): string | null => {
  const w = String(v || "").trim().toUpperCase().replace(/ /g, "_");
  return APPROVE_WORDS.has(w) ? APPROVE : CHANGES_WORDS.has(w) ? REQUEST_CHANGES : null;
};
function parseFindings(items: unknown): Finding[] {
  if (!Array.isArray(items)) return [];
  return items.filter((i) => i && typeof i === "object" && !Array.isArray(i)).map((i: any) => {
    const n = parseInt(i.line ?? 0, 10);
    return mkFinding({ file: String(i.file || i.path || ""), line: Number.isNaN(n) ? 0 : n, severity: String(i.severity || "nit").toLowerCase(), issue: String(i.issue || i.message || i.problem || ""),
      evidence: String(i.evidence || i.snippet || i.quote || i.code || ""), suggestion: typeof i.suggestion === "string" ? i.suggestion : "" });
  });
}
/** Parse a model answer into a verdict; null when unusable. */
export function parseReview(text: string | null | undefined, model = ""): ReviewVerdict | null {
  if (!text) return null;
  const d = extractJson(text); if (!d) return null;
  const verdict = normalizeVerdict(d.verdict || d.decision); if (!verdict) return null;
  return mkVerdict({ verdict, summary: String(d.summary || "").trim(), findings: parseFindings(d.findings), model });
}

const sev = (f: Finding) => ORDER[(f.severity || "nit").toLowerCase()] ?? 0;
/**
 * Final verdict from the findings that survived grounding/verification, not from the model's own label: a confirmed `error`
 * always blocks; a REQUEST_CHANGES whose blocking claims were all discarded becomes APPROVE; otherwise the model's call stands.
 */
export function decide(v: ReviewVerdict, dropped: number): ReviewVerdict {
  const errors = v.findings.filter((f) => sev(f) >= 2).length, warns = v.findings.filter((f) => sev(f) === 1).length;
  const verdict = errors ? REQUEST_CHANGES : v.verdict === REQUEST_CHANGES && !warns && dropped ? APPROVE : v.verdict;
  if (!dropped && verdict === v.verdict) return v;
  const kept = v.findings.length ? `${v.findings.length} achado(s) confirmado(s) (${errors} error, ${warns} warn).` : "Nenhum achado se sustentou.";
  const gone = dropped ? ` ${dropped} alegação(ões) do modelo descartada(s): sem evidência no código ou refutada(s) na verificação.` : "";
  return { ...v, verdict, summary: dropped ? kept + gone : `${v.summary} ${kept}`.trim() };
}

function renderFindings(v: ReviewVerdict): string {
  if (!v.findings.length) return isApproved(v) ? "Sem pontos bloqueantes. 🎉" : "Nenhum detalhe adicional informado.";
  if (isApproved(v)) return "**Pontos de atenção (não bloqueantes):**\n" + v.findings.map((f) => `- 🟡 \`${f.file}\`${f.line ? `:${f.line}` : ""} — ${f.issue}`).join("\n");
  const rows = v.findings.map((f) => `| ${ICON[f.severity] ?? "🟡"} ${f.severity} | \`${f.file}\` | ${f.line || "-"} | ${f.issue} |`);
  return ["| Severidade | Arquivo | Linha | Problema |", "|---|---|---|---|", ...rows].join("\n");
}
function renderFixes(v: ReviewVerdict): string {
  if (isApproved(v)) return "";
  return v.fixed ? `✅ Correções aplicadas e enviadas para este PR no commit \`${(v.commit || "").slice(0, 8)}\`.` : "ℹ️ Nenhuma correção automática foi aplicada.";
}
const skillsText = (v: ReviewVerdict) => (v.skills_used.length ? "skills usadas " + v.skills_used.map((s) => `\`${s}\``).join(", ") : v.skills_checked ? "nenhuma skill invocada" : "skills não registradas");

/** Standardized, emoji-tagged PT-BR review comment. */
export function buildReviewComment(v: ReviewVerdict, headSha = ""): string {
  const ok = isApproved(v);
  const summary = v.summary || (ok ? "Tudo certo por aqui." : "Encontrei pontos a corrigir.");
  const footer = `<sub>🤖 Revisão automática via ${v.harness ? `\`${v.harness}\`` : "opencode"} · modelo \`${v.model || "cloud/auto"}\` · ${skillsText(v)}${headSha ? ` · SHA \`${headSha.slice(0, 8)}\`` : ""}</sub>`;
  const parts = [REVIEW_MARKER, ok ? "## ✅ Revisão aprovada! 🎉🚀" : "## ❌ Mudanças sugeridas 🛠️", `**Resumo:** ${summary}`, "### 🔎 Achados", renderFindings(v)];
  const fixes = renderFixes(v); if (fixes) parts.push("### 🛠️ Correções", fixes);
  if (isCritical(v)) parts.push("### 🚨 Crítico", `Achados de severidade \`error\` bloqueiam o merge (draft + check \`${GATE_NAME}\`) até serem corrigidos por um novo commit.`);
  parts.push(`**Veredito:** \`${v.verdict}\` · label \`${verdictLabel(v)}\``, blocks(v) ? "*Achados bloqueantes impedem o merge até serem corrigidos.*" : "*Comentário consultivo — não bloqueia o merge.*", footer, "---", buildOriginMetadata("pr_assistant", v.model || "cloud/auto"));
  return parts.filter(Boolean).join("\n\n");
}
