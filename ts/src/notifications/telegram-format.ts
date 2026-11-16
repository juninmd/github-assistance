/** Shared Telegram layout: one card shape (title, repo, PR link, details) and PT-BR labels for internal reason codes. */
import { TelegramNotifier } from "./telegram.ts";

export const esc = TelegramNotifier.escapeHtml;
export const SEP = "──────────────────────";
const REASON_LABELS: Record<string, string> = {
  pr_too_young: "PR recente (aguardando idade mínima)", "auto-merge-skip": "label auto-merge-skip", untrusted_author: "autor não confiável",
  has_conflicts: "conflito de merge", mergeable_unknown: "GitHub ainda calculando mergeabilidade", pipeline_failure: "pipeline falhou",
  pipeline_fix_attempted: "correção de pipeline enviada", pipeline_pending: "pipeline em andamento", pipeline_queued: "pipeline na fila",
  review_blocked: "revisão encontrou problema crítico", review_pending: "revisão ainda não executada (tenta na próxima rodada)",
  simulation: "modo simulação", merge_failed: "merge falhou", mergeable_state_unknown: "estado de merge desconhecido", autonomy_mode: "autonomia do repo não permite merge",
  update_branch_failed: "falha ao atualizar branch", refresh_failed: "falha ao reler o PR", billing_blocked_credential_found: "credencial encontrada com CI bloqueado por billing",
  error: "erro inesperado",
};
export const reasonLabel = (reason: string): string => { const key = String(reason).split(/[:|]/)[0]!.trim(); return REASON_LABELS[key] ?? key.replace(/[_-]/g, " "); };
export const prButton = (pr: { html_url?: string }) => ({ inline_keyboard: [[{ text: "🔗 Ver PR no GitHub", url: pr.html_url ?? "" }]] });
export function card(icon: string, title: string, pr: any, details: string[] = []): string {
  const head = [`${icon} <b>${title}</b>`, SEP, `📦 <b>Repo:</b> <code>${esc(pr.base?.repo?.full_name ?? "unknown")}</code>`,
    `🔀 <b>PR:</b> <a href="${pr.html_url}">#${pr.number}</a> — ${esc(pr.title)}`];
  if (pr.head?.ref) head.push(`🌿 <b>Branch:</b> <code>${esc(pr.head.ref)}</code> ➔ <code>${esc(pr.base?.ref ?? "?")}</code>`);
  return [...head, ...details].join("\n");
}
