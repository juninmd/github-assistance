import { TelegramNotifier } from "../../notifications/telegram.ts";
const esc = TelegramNotifier.escapeHtml;

export function buildFindingMessage(repo: string, finding: Record<string, any>, originalLine: string, action: string): string {
  const remove = action === "REMOVE_FROM_HISTORY";
  const preview = originalLine ? esc(originalLine.slice(0, 200)) : "<i>não disponível</i>";
  return `${remove ? "🔥" : "✅"} <b>Secret ${remove ? "Removida do Histórico" : "Falso Positivo (Ignorado)"}</b>\n\n` +
    `📦 Repositório: <code>${esc(repo)}</code>\n📄 Arquivo: <code>${esc(finding.file ?? "unknown")}</code> (Linha ${finding.line ?? 0})\n` +
    `🤖 Motivo: <i>${esc(finding._reason ?? "No reason provided")}</i>\n\n📝 <b>Conteúdo original (redactado):</b>\n<code>${preview}</code>`;
}
export const getFindingButtons = (repoUrl: string, commitUrl: string, fileLineUrl: string) =>
  [[{ text: "🔗 Repositório", url: repoUrl }, { text: "📌 Commit", url: commitUrl }], [{ text: "📄 Arquivo+Linha", url: fileLineUrl }]];

export const sendFindingNotification = (t: TelegramNotifier, o: { repo: string; finding: Record<string, any>; action: string; originalLine: string; commitUrl: string; fileLineUrl: string; repoUrl: string }) =>
  t.sendMessage(buildFindingMessage(o.repo, o.finding, o.originalLine, o.action), "HTML", { inline_keyboard: getFindingButtons(o.repoUrl, o.commitUrl, o.fileLineUrl) });
export const sendErrorNotification = (t: TelegramNotifier, owner: string, msg: string) =>
  t.sendMessage(`🔐 <b>Secret Remover — Erro</b>\n\n❌ ${esc(msg)}\n\n👤 Owner: <code>${esc(owner)}</code>`, "HTML");
